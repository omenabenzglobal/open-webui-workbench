"""
Workbench Backend API Router
Module: backend.open_webui.apps.workbench.api
Prefix: /api/v1/workbench

Exposes isolated endpoints for:
- Workspace file tree inspection and file reading/writing
- Sandboxed terminal command execution
- Autonomous task creation, retrieval, and background execution
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import shlex
import sys
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field

from open_webui.apps.workbench.runtime.engine import AutonomousAgentEngine
from open_webui.apps.workbench.runtime.schema import TaskRecord, TaskStatus, TaskStore
from open_webui.apps.workbench.security.exceptions import (
    PathTraversalError,
    PolicyViolationError,
    SecurityException,
)
from open_webui.apps.workbench.security.executor import CommandResult, SafeExecutor
from open_webui.apps.workbench.security.policy import ExecutionMode, PolicyEngine
from open_webui.apps.workbench.security.workspace import WorkspaceBoundary
from open_webui.apps.workbench.tools.workspace_tools import Tools

log = logging.getLogger(__name__)

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Workspace & Runtime State Singletons
# ─────────────────────────────────────────────────────────────────────────────

WORKSPACE_DIR = Path("./workspace").resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

workspace_boundary = WorkspaceBoundary(WORKSPACE_DIR)
policy_engine = PolicyEngine()
safe_executor = SafeExecutor(default_timeout_seconds=30)
task_store = TaskStore()
workspace_tools = Tools()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────────────────────

class FileWriteRequest(BaseModel):
    path: str = Field(..., description="Relative path within workspace")
    content: str = Field(..., description="File content to write")


class TerminalExecRequest(BaseModel):
    command: str = Field(..., description="Shell command string to execute")
    timeout: Optional[int] = Field(30, description="Execution timeout in seconds")


class TaskCreateRequest(BaseModel):
    prompt: Optional[str] = Field("", description="Objective / instruction for the agent")
    description: Optional[str] = Field("", description="Objective / description alias")
    title: Optional[str] = Field("", description="Optional human-readable title")
    model: Optional[str] = Field("", description="Target model name")
    step_limit: Optional[int] = Field(0, description="Maximum autonomous steps (0 = unlimited)")


# ─────────────────────────────────────────────────────────────────────────────
# Provider Helper for Background Task Execution
# ─────────────────────────────────────────────────────────────────────────────

def _get_provider_credentials() -> Dict[str, str]:
    """Dynamically scan environment and Windows registry for active keys."""
    creds = {}
    known_keys = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "DEEPSEEK_API_KEY",
    ]
    for k in known_keys:
        val = os.environ.get(k)
        if val:
            creds[k] = val

    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as reg_key:
                for k in known_keys:
                    if k not in creds:
                        try:
                            val, _ = winreg.QueryValueEx(reg_key, k)
                            if val:
                                creds[k] = val
                        except FileNotFoundError:
                            pass
        except Exception:
            pass
    return creds


async def default_provider_adapter(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Default provider adapter routing to active provider endpoint or returning
    completion fallback if offline.  Uses async httpx for true non-blocking I/O.
    """
    import httpx

    creds = _get_provider_credentials()
    gemini_key = creds.get("GEMINI_API_KEY") or creds.get("GOOGLE_API_KEY")
    openai_key = creds.get("OPENAI_API_KEY")

    if gemini_key:
        endpoint_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        api_key = gemini_key
        models_to_try = [
            "models/gemini-flash-lite-latest",
            "models/gemini-3.5-flash",
            "models/gemini-flash-latest",
        ]
    elif openai_key:
        endpoint_url = "https://api.openai.com/v1/chat/completions"
        api_key = openai_key
        models_to_try = ["gpt-4o-mini"]
    else:
        # Offline fallback for testing environments
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "No active provider API key configured. Task initialized in offline mode.",
                }
            }]
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        for attempt in range(9):
            model_name = models_to_try[attempt % len(models_to_try)]
            payload = {
                "model": model_name,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
            try:
                resp = await client.post(endpoint_url, headers=headers, json=payload)
                if resp.status_code in (429, 500, 502, 503) and attempt < 8:
                    wait_time = (attempt // len(models_to_try) + 1) * 5
                    log.warning(
                        "Provider %s HTTP %d, rotating model in %ds (attempt %d/9)…",
                        model_name,
                        resp.status_code,
                        wait_time,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as err:
                if err.response.status_code in (429, 500, 502, 503) and attempt < 8:
                    wait_time = (attempt // len(models_to_try) + 1) * 5
                    log.warning(
                        "Provider %s HTTP %d, rotating model in %ds (attempt %d/9)…",
                        model_name,
                        err.response.status_code,
                        wait_time,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise
            except (httpx.ConnectError, httpx.TimeoutException) as err:
                if attempt < 8:
                    wait_time = (attempt + 1) * 5
                    log.warning(
                        "Provider network error %s, retrying in %ds (attempt %d/9)…",
                        err,
                        wait_time,
                        attempt + 1,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise


# ─────────────────────────────────────────────────────────────────────────────
# 1. System Health & Execution Mode
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Returns workbench health, current execution policy mode, and workspace path."""
    return {
        "status": "ok",
        "service": "OMENA Autonomous Agent Workbench",
        "version": "1.0.0",
        "execution_mode": "AUTONOMOUS",
        "workspace_root": str(workspace_boundary.root_path),
        "tasks_total": len(task_store.list_tasks(limit=1000)),
        "timestamp": time.time(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Workspace File Tree & File I/O
# ─────────────────────────────────────────────────────────────────────────────

def _build_tree_recursive(boundary: WorkspaceBoundary, current_dir: Path) -> Dict[str, Any]:
    """Recursively constructs a clean JSON tree of the workspace directory."""
    try:
        rel_path = str(current_dir.relative_to(boundary.root_path)).replace("\\", "/")
    except ValueError:
        rel_path = "."
    if rel_path == ".":
        rel_path = ""

    node: Dict[str, Any] = {
        "name": current_dir.name if rel_path else "workspace",
        "path": rel_path if rel_path else ".",
        "is_dir": True,
        "children": [],
    }

    try:
        entries = sorted(
            current_dir.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
        for entry in entries:
            # Skip noise / hidden files
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            if entry.is_dir():
                node["children"].append(_build_tree_recursive(boundary, entry))
            else:
                try:
                    stat = entry.stat()
                    entry_rel = str(entry.relative_to(boundary.root_path)).replace("\\", "/")
                    node["children"].append({
                        "name": entry.name,
                        "path": entry_rel,
                        "is_dir": False,
                        "size": stat.st_size,
                        "modified_at": stat.st_mtime,
                    })
                except (OSError, PermissionError):
                    continue
    except (PermissionError, OSError):
        pass

    return node


@router.get("/workspace/tree")
@router.get("/files/list")
async def get_workspace_tree():
    """Returns recursive JSON directory tree of the workspace."""
    workspace_boundary.ensure_workspace()
    tree = _build_tree_recursive(workspace_boundary, workspace_boundary.root_path)
    return tree


@router.get("/workspace/file")
@router.get("/files/read")
async def read_workspace_file(path: str = Query(..., description="Relative path within workspace")):
    """Reads text file contents up to 50KB."""
    try:
        content = workspace_boundary.read_file(path, max_bytes=51200)
        return {
            "path": path,
            "content": content,
            "size": len(content.encode("utf-8")),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (PathTraversalError, SecurityException) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/workspace/file")
@router.post("/files/write")
async def write_workspace_file(req: FileWriteRequest):
    """Writes text file within the workspace boundary."""
    try:
        bytes_written = workspace_boundary.write_file(req.path, req.content)
        return {
            "status": "ok",
            "path": req.path,
            "bytes_written": bytes_written,
        }
    except (PathTraversalError, SecurityException) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 3. Terminal Execution
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/terminal/exec")
async def execute_terminal_command(req: TerminalExecRequest):
    """Executes a command via SafeExecutor in AUTONOMOUS mode within the workspace."""
    cmd_clean = req.command.strip()
    if not cmd_clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Command cannot be empty")

    # Evaluate against policy engine in AUTONOMOUS mode
    decision = policy_engine.evaluate_action(
        mode=ExecutionMode.AUTONOMOUS,
        action_type="command",
        command_or_path=cmd_clean,
    )
    if decision.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Command permanently blocked by security policy: {decision.reason}",
        )

    # Tokenize arguments
    try:
        if os.name == "nt":
            raw_args = shlex.split(cmd_clean, posix=False)
            cmd_args = [
                arg[1:-1]
                if len(arg) >= 2 and ((arg[0] == '"' and arg[-1] == '"') or (arg[0] == "'" and arg[-1] == "'"))
                else arg
                for arg in raw_args
            ]
        else:
            cmd_args = shlex.split(cmd_clean, posix=True)
    except Exception:
        cmd_args = cmd_clean.split()

    if not cmd_args:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid command syntax")

    timeout = req.timeout if req.timeout and req.timeout > 0 else 30

    res = await safe_executor.run_command(
        cmd=cmd_args,
        cwd=workspace_boundary.root_path,
        timeout_seconds=timeout,
    )

    return {
        "command": cmd_clean,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "exit_code": res.exit_code,
        "duration_ms": int(res.duration_seconds * 1000),
        "timed_out": res.timed_out,
        "truncated": res.truncated,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Autonomous Task Orchestration
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(limit: int = 50, status_filter: Optional[str] = None):
    """Lists recent tasks with state and progress."""
    filter_enum = None
    if status_filter:
        try:
            filter_enum = TaskStatus(status_filter.upper())
        except ValueError:
            pass
    tasks = task_store.list_tasks(status_filter=filter_enum, limit=limit)
    return [t.to_dict() for t in tasks]


@router.post("/tasks/create")
@router.post("/tasks")
async def create_task(req: TaskCreateRequest):
    """Registers a new autonomous task in the persistent TaskStore."""
    prompt_text = req.prompt or req.description or req.title or "Autonomous Task"
    record = task_store.create_task(
        prompt=prompt_text,
        title=req.title or prompt_text[:30],
        step_limit=req.step_limit or 0,
    )
    # Initialize conversation history with the user prompt
    task_store.update_task(
        record.task_id,
        history=[{"role": "user", "content": prompt_text}],
        status=TaskStatus.PENDING,
    )
    return {
        "id": record.task_id,
        "task_id": record.task_id,
        "title": record.title,
        "status": record.status.value,
        "current_step": 0,
        "step_limit": record.step_limit,
    }


@router.get("/tasks/{task_id}")
async def get_task_details(task_id: str):
    """Returns the serialized state, step count, and full history of a task."""
    record = task_store.get_task(task_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")
    data = record.to_dict()
    data["history"] = record.history
    return data


async def _run_task_background(task_id: str):
    """Background runner for autonomous task completion."""
    engine = AutonomousAgentEngine(
        tools_instance=workspace_tools,
        provider_fn=default_provider_adapter,
        store=task_store,
    )
    try:
        await engine.run_to_completion(task_id)
    except Exception as e:
        log.error(f"Background task run failed for {task_id}: {e}")
        task_store.update_task(task_id, status=TaskStatus.FAILED)


_running_background_tasks = set()


@router.post("/tasks/{task_id}/run")
async def run_task(
    task_id: str,
    force: bool = False,
):
    """Triggers autonomous background execution for an existing task."""
    record = task_store.get_task(task_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")

    if record.status == TaskStatus.RUNNING and not force:
        return {"task_id": task_id, "status": "RUNNING", "message": "Task is already executing"}

    task_store.update_task(task_id, status=TaskStatus.RUNNING)
    t = asyncio.create_task(_run_task_background(task_id))
    _running_background_tasks.add(t)
    t.add_done_callback(_running_background_tasks.discard)

    return {
        "task_id": task_id,
        "status": "RUNNING",
        "message": "Autonomous task execution scheduled",
    }
