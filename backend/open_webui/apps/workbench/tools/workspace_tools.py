"""
Workbench Workspace Tools
Module: backend.open_webui.apps.workbench.tools.workspace_tools

Exposes secure workspace operations (read_file, write_file, list_files, execute_command)
as native Open WebUI Tools governed by WorkspaceBoundary, PolicyEngine, and SafeExecutor.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
import shlex
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from open_webui.apps.workbench.security.exceptions import (
    PathTraversalError,
    PolicyViolationError,
    SecurityException,
)
from open_webui.apps.workbench.security.executor import CommandResult, SafeExecutor
from open_webui.apps.workbench.security.policy import ExecutionMode, PolicyEngine, RiskLevel
from open_webui.apps.workbench.security.workspace import WorkspaceBoundary


class Tools:
    """
    Open WebUI Native Tool Suite providing sandboxed developer workspace operations.
    """

    class Valves(BaseModel):
        WORKSPACE_ROOT: str = Field(
            default="./workspace",
            description="Absolute or relative root path for the confined developer workspace.",
        )
        EXECUTION_MODE: str = Field(
            default="AUTONOMOUS",
            description="Execution policy mode: SAFE, ASSISTED, or AUTONOMOUS.",
        )
        TIMEOUT_SECONDS: int = Field(
            default=30,
            description="Command execution timeout in seconds.",
        )

    def __init__(self, valves: Optional[Tools.Valves] = None):
        self.valves = valves or self.Valves()
        self.policy_engine = PolicyEngine()
        root = Path(self.valves.WORKSPACE_ROOT).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.workspace_boundary = WorkspaceBoundary(root)
        self.safe_executor = SafeExecutor(default_timeout_seconds=self.valves.TIMEOUT_SECONDS)
        self._cached_root = root

    @property
    def boundary(self) -> WorkspaceBoundary:
        root = Path(self.valves.WORKSPACE_ROOT).resolve()
        if not hasattr(self, "_cached_root") or self._cached_root != root:
            root.mkdir(parents=True, exist_ok=True)
            self.workspace_boundary = WorkspaceBoundary(root)
            self._cached_root = root
        return self.workspace_boundary

    @property
    def executor(self) -> SafeExecutor:
        timeout = self.valves.TIMEOUT_SECONDS
        if not hasattr(self, "safe_executor") or self.safe_executor.default_timeout_seconds != timeout:
            self.safe_executor = SafeExecutor(default_timeout_seconds=timeout)
        return self.safe_executor

    def _get_execution_mode(self) -> ExecutionMode:
        mode_str = str(self.valves.EXECUTION_MODE).upper().strip()
        try:
            return ExecutionMode(mode_str)
        except ValueError:
            return ExecutionMode.SAFE

    async def _emit_status(
        self,
        emitter: Optional[Callable[[Dict[str, Any]], Any]],
        description: str,
        done: bool = False,
    ) -> None:
        if not emitter:
            return
        payload = {
            "type": "status",
            "data": {
                "description": description,
                "done": done,
            },
        }
        try:
            if inspect.iscoroutinefunction(emitter):
                await emitter(payload)
            elif callable(emitter):
                res = emitter(payload)
                if inspect.isawaitable(res):
                    await res
        except Exception:
            # Event emission failures should never crash tool execution
            pass

    async def list_files(
        self,
        subpath: str = ".",
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> str:
        """
        List files and directories in the confined workspace directory.

        :param subpath: Relative path within the workspace to list. Defaults to root ('.').
        :return: JSON formatted list of directory entries or error message.
        """
        await self._emit_status(__event_emitter__, f"Listing files in {subpath}...", done=False)
        try:
            mode = self._get_execution_mode()
            decision = self.policy_engine.evaluate_action(mode=mode, action_type="list", command_or_path=subpath)
            if decision.is_blocked:
                err_msg = f"Error: Policy blocked directory listing. Reason: {decision.reason}"
                await self._emit_status(__event_emitter__, err_msg, done=True)
                return err_msg

            boundary = self.boundary
            entries = boundary.list_dir(subpath)
            result = json.dumps(entries, indent=2)
            await self._emit_status(__event_emitter__, f"Listed {len(entries)} entries in {subpath}", done=True)
            return result
        except SecurityException as e:
            err_msg = f"Security Error: {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg
        except Exception as e:
            err_msg = f"Error listing directory '{subpath}': {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

    async def read_file(
        self,
        path: str,
        max_bytes: int = 50000,
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> str:
        """
        Read content from a file within the confined workspace.

        :param path: Relative path of the file to read within the workspace.
        :param max_bytes: Maximum number of bytes to read. Defaults to 50000.
        :return: File content as text, or error message.
        """
        await self._emit_status(__event_emitter__, f"Reading {path}...", done=False)
        try:
            mode = self._get_execution_mode()
            decision = self.policy_engine.evaluate_action(mode=mode, action_type="read", command_or_path=path)
            if decision.is_blocked:
                err_msg = f"Error: Policy blocked read action. Reason: {decision.reason}"
                await self._emit_status(__event_emitter__, err_msg, done=True)
                return err_msg

            boundary = self.boundary
            content = boundary.read_file(path, max_bytes=max_bytes)
            await self._emit_status(__event_emitter__, f"Read {len(content)} characters from {path}", done=True)
            return content
        except SecurityException as e:
            err_msg = f"Security Error: {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg
        except FileNotFoundError:
            err_msg = f"Error: File not found: {path}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg
        except Exception as e:
            err_msg = f"Error reading file '{path}': {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

    async def write_file(
        self,
        path: str,
        content: str,
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> str:
        """
        Write content to a file within the confined workspace.

        :param path: Relative path of the file to write within the workspace.
        :param content: Content string to write to the file.
        :return: Confirmation message with byte count written, or error message.
        """
        await self._emit_status(__event_emitter__, f"Writing to {path}...", done=False)
        try:
            mode = self._get_execution_mode()
            decision = self.policy_engine.evaluate_action(mode=mode, action_type="write", command_or_path=path)
            if decision.is_blocked:
                err_msg = f"Error: Policy blocked write action. Reason: {decision.reason}"
                await self._emit_status(__event_emitter__, err_msg, done=True)
                return err_msg
            if decision.requires_confirmation:
                err_msg = f"Notice: Action requires user confirmation. Reason: {decision.reason}"
                await self._emit_status(__event_emitter__, err_msg, done=True)
                return err_msg

            boundary = self.boundary
            bytes_written = boundary.write_file(path, content)
            msg = f"Successfully wrote {bytes_written} bytes to {path}"
            await self._emit_status(__event_emitter__, msg, done=True)
            return msg
        except SecurityException as e:
            err_msg = f"Security Error: {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg
        except Exception as e:
            err_msg = f"Error writing file '{path}': {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

    async def execute_command(
        self,
        command: str,
        __event_emitter__: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> str:
        """
        Execute a system command within the confined workspace under strict safety policies.

        :param command: Shell or CLI command string to execute.
        :return: Execution summary including exit code, stdout, and stderr.
        """
        await self._emit_status(__event_emitter__, f"Evaluating command: {command}...", done=False)
        cmd_clean = command.strip()
        if not cmd_clean:
            err_msg = "Error: Command cannot be empty."
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

        mode = self._get_execution_mode()
        decision = self.policy_engine.evaluate_action(mode=mode, action_type="execute", command_or_path=cmd_clean)

        if decision.is_blocked:
            err_msg = f"Error: Policy blocked command execution. Risk: {decision.risk_level.value}. Reason: {decision.reason}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

        if decision.requires_confirmation:
            err_msg = f"Notice: Command requires confirmation. Risk: {decision.risk_level.value}. Reason: {decision.reason}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

        has_shell_ops = any(op in cmd_clean for op in ["|", "&&", "||", ";", ">", "<", "$", "`"])
        if has_shell_ops:
            if os.name == "nt":
                cmd_args = ["cmd.exe", "/c", cmd_clean]
            else:
                cmd_args = ["/bin/bash", "-c", cmd_clean]
        else:
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
            err_msg = "Error: Unable to parse command arguments."
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg

        await self._emit_status(__event_emitter__, f"Executing command: {cmd_args[0]}...", done=False)

        boundary = self.boundary
        workspace_root = boundary.root_path

        try:
            result = await self.executor.run_command(
                cmd=cmd_args,
                cwd=workspace_root,
                timeout_seconds=self.valves.TIMEOUT_SECONDS,
            )

            status_msg = f"Command finished with exit code {result.exit_code} in {result.duration_seconds:.2f}s"
            await self._emit_status(__event_emitter__, status_msg, done=True)

            report_lines = [
                f"Command: {cmd_clean}",
                f"Exit Code: {result.exit_code}",
                f"Duration: {result.duration_seconds:.2f}s",
            ]
            if result.timed_out:
                report_lines.append("Status: TIMED OUT")
            if result.truncated:
                report_lines.append("Notice: Output was truncated to buffer limits")
            if result.stdout:
                report_lines.append(f"\n--- STDOUT ---\n{result.stdout.strip()}")
            if result.stderr:
                report_lines.append(f"\n--- STDERR ---\n{result.stderr.strip()}")

            return "\n".join(report_lines)
        except SecurityException as e:
            err_msg = f"Security Error: {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg
        except Exception as e:
            err_msg = f"Execution Error: {e}"
            await self._emit_status(__event_emitter__, err_msg, done=True)
            return err_msg
