"""
Integration & Unit Test Suite: Durable Agent Runtime
Test Module: backend.open_webui.apps.workbench.tests.test_agent_runtime
Directive: DIR-4.1-DURABLE-TASK-RUNTIME

Tests cover:
1. State persistence (SQLite CRUD for TaskStore)
2. Loop progression with mocked provider (write → execute → final text)
3. Autonomous self-healing with mocked provider (error → reflection → fix → success)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

# Ensure WEBUI_SECRET_KEY is present for Open WebUI imports
os.environ.setdefault("WEBUI_SECRET_KEY", "test-secret-key-for-runtime-tests")

from open_webui.apps.workbench.runtime.schema import (
    TaskRecord,
    TaskStatus,
    TaskStore,
)
from open_webui.apps.workbench.runtime.recovery import (
    extract_error_from_receipt,
    format_error_reflection,
)
from open_webui.apps.workbench.runtime.engine import (
    AutonomousAgentEngine,
    TaskResult,
    TaskStepResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def memory_store():
    """Create an in-memory TaskStore for isolated tests."""
    return TaskStore(db_path=":memory:")


@pytest.fixture
def file_store(tmp_path):
    """Create a file-backed TaskStore for persistence tests."""
    db_path = str(tmp_path / "test_tasks.db")
    return TaskStore(db_path=db_path), db_path


class MockTools:
    """
    Minimal mock of workspace_tools.Tools that records calls and returns
    configurable responses.  Does not require WorkspaceBoundary or PolicyEngine.
    """

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        self.calls: List[Dict[str, Any]] = []
        self._custom_responses: Dict[str, str] = {}

    def set_response(self, fn_name: str, response: str) -> None:
        """Pre-configure a response for a specific tool call."""
        self._custom_responses[fn_name] = response

    async def write_file(self, path: str, content: str, **kwargs) -> str:
        self.calls.append({"fn": "write_file", "path": path, "content": content})
        if "write_file" in self._custom_responses:
            return self._custom_responses["write_file"]
        # Actually write the file
        full_path = Path(self.workspace_dir) / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return json.dumps({"status": "success", "path": path, "bytes_written": len(content)})

    async def read_file(self, path: str, **kwargs) -> str:
        self.calls.append({"fn": "read_file", "path": path})
        if "read_file" in self._custom_responses:
            return self._custom_responses["read_file"]
        full_path = Path(self.workspace_dir) / path
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return "Error: File not found"

    async def list_files(self, subpath: str = ".", **kwargs) -> str:
        self.calls.append({"fn": "list_files", "subpath": subpath})
        if "list_files" in self._custom_responses:
            return self._custom_responses["list_files"]
        return json.dumps(["file1.py", "file2.py"])

    async def execute_command(self, command: str, **kwargs) -> str:
        self.calls.append({"fn": "execute_command", "command": command})
        if "execute_command" in self._custom_responses:
            return self._custom_responses["execute_command"]
        return json.dumps({
            "exit_code": 0,
            "stdout": "Command executed successfully",
            "stderr": "",
            "command": command,
        })


def make_mock_provider(responses: List[Dict[str, Any]]):
    """
    Create a mock provider function that returns pre-configured responses
    in sequence.  Each response should be an OpenAI-compatible chat completion
    response dict.
    """
    call_index = [0]

    async def provider_fn(
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        idx = call_index[0]
        if idx >= len(responses):
            # Default: return a final text response
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Task complete (no more mock responses).",
                    }
                }]
            }
        call_index[0] += 1
        return responses[idx]

    return provider_fn


# ─────────────────────────────────────────────────────────────────────────────
# 1. State Persistence Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_task_store_create_and_retrieve(memory_store):
    """Verify creating a task writes to SQLite and retrieval returns correct data."""
    store = memory_store

    record = store.create_task(
        prompt="Write a Python factorial function",
        title="Factorial Task",
        step_limit=10,
    )

    assert record.task_id is not None
    assert record.title == "Factorial Task"
    assert record.status == TaskStatus.PENDING
    assert record.prompt == "Write a Python factorial function"
    assert record.current_step == 0
    assert record.step_limit == 10
    assert record.history == []
    assert record.created_at > 0
    assert record.updated_at > 0

    # Retrieve the same task
    loaded = store.get_task(record.task_id)
    assert loaded is not None
    assert loaded.task_id == record.task_id
    assert loaded.title == record.title
    assert loaded.status == TaskStatus.PENDING
    assert loaded.prompt == record.prompt


def test_task_store_update_and_checkpoint(memory_store):
    """Verify updating task state (status, step, history) persists correctly."""
    store = memory_store
    record = store.create_task(prompt="Test checkpoint")

    # Simulate a step: update status, step counter, and history
    test_history = [
        {"role": "user", "content": "Test checkpoint"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "function": {"name": "write_file", "arguments": '{"path":"a.py","content":"x=1"}'}}
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"status":"success"}'},
    ]

    updated = store.update_task(
        record.task_id,
        status=TaskStatus.RUNNING,
        current_step=1,
        history=test_history,
    )

    assert updated is not None
    assert updated.status == TaskStatus.RUNNING
    assert updated.current_step == 1
    assert len(updated.history) == 3
    assert updated.history[0]["role"] == "user"
    assert updated.history[1]["role"] == "assistant"
    assert updated.history[2]["role"] == "tool"
    assert updated.updated_at >= record.updated_at


def test_task_store_file_persistence(file_store):
    """Verify task state survives across TaskStore instances (DB file persistence)."""
    store1, db_path = file_store

    record = store1.create_task(prompt="Persistent task test")
    task_id = record.task_id

    # Update via first store instance
    store1.update_task(
        task_id,
        status=TaskStatus.RUNNING,
        current_step=3,
        history=[{"role": "user", "content": "test"}],
    )

    # Create a completely new store instance pointing to the same DB file
    store2 = TaskStore(db_path=db_path)

    # Verify state survived
    loaded = store2.get_task(task_id)
    assert loaded is not None
    assert loaded.task_id == task_id
    assert loaded.status == TaskStatus.RUNNING
    assert loaded.current_step == 3
    assert len(loaded.history) == 1
    assert loaded.history[0]["content"] == "test"


def test_task_store_list_and_delete(memory_store):
    """Verify listing tasks with filters and deletion."""
    store = memory_store

    # Create multiple tasks
    t1 = store.create_task(prompt="Task 1")
    t2 = store.create_task(prompt="Task 2")
    t3 = store.create_task(prompt="Task 3")

    store.update_task(t1.task_id, status=TaskStatus.COMPLETED)
    store.update_task(t2.task_id, status=TaskStatus.RUNNING)

    # List all
    all_tasks = store.list_tasks()
    assert len(all_tasks) == 3

    # List filtered
    completed = store.list_tasks(status_filter=TaskStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].task_id == t1.task_id

    running = store.list_tasks(status_filter=TaskStatus.RUNNING)
    assert len(running) == 1
    assert running[0].task_id == t2.task_id

    # Delete
    assert store.delete_task(t3.task_id) is True
    assert store.get_task(t3.task_id) is None
    assert len(store.list_tasks()) == 2


def test_task_store_nonexistent_task(memory_store):
    """Verify get/update return None for non-existent task IDs."""
    store = memory_store
    assert store.get_task("nonexistent-id") is None
    assert store.update_task("nonexistent-id", status=TaskStatus.FAILED) is None
    assert store.delete_task("nonexistent-id") is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Recovery Module Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_error_reflection_formatting():
    """Verify format_error_reflection produces structured diagnostic output."""
    result = format_error_reflection(
        tool_name="execute_command",
        exit_code=1,
        stdout="",
        stderr="NameError: name 'undefined_var' is not defined",
        command="python broken.py",
    )

    assert "Tool Execution Error" in result
    assert "execute_command" in result
    assert "Exit Code: 1" in result
    assert "python broken.py" in result
    assert "NameError" in result
    assert "corrective action" in result.lower()


def test_error_reflection_truncation():
    """Verify large stderr output is truncated while preserving diagnostics."""
    huge_stderr = "X" * 10000
    result = format_error_reflection(
        tool_name="execute_command",
        exit_code=1,
        stderr=huge_stderr,
    )
    assert "truncated" in result.lower()
    assert len(result) < len(huge_stderr)


def test_extract_error_from_receipt_success():
    """Verify successful receipt returns None (no error)."""
    receipt = json.dumps({"exit_code": 0, "stdout": "ok", "stderr": ""})
    assert extract_error_from_receipt(receipt) is None


def test_extract_error_from_receipt_failure():
    """Verify failed receipt extracts error fields correctly."""
    receipt = json.dumps({
        "exit_code": 1,
        "stdout": "partial output",
        "stderr": "SyntaxError: invalid syntax",
        "command": "python test.py",
    })
    error_info = extract_error_from_receipt(receipt)
    assert error_info is not None
    assert error_info["exit_code"] == 1
    assert "SyntaxError" in error_info["stderr"]
    assert error_info["command"] == "python test.py"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Engine Loop Progression Test (Mocked Provider)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_engine_loop_progression():
    """
    Verify run_to_completion executes a 3-step sequence:
      Step 1: Model calls write_file
      Step 2: Model calls execute_command
      Step 3: Model produces final text
    Verify status transitions PENDING → RUNNING → COMPLETED.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_tools = MockTools(workspace_dir=tmp_dir)
        store = TaskStore(db_path=":memory:")

        # Define the 3-step mock provider response sequence
        mock_responses = [
            # Step 1: Model emits write_file tool call
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_write_1",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({
                                    "path": "calc.py",
                                    "content": "def factorial(n):\n    return 1 if n <= 1 else n * factorial(n-1)\nprint(factorial(5))\n",
                                }),
                            },
                        }],
                    }
                }]
            },
            # Step 2: Model emits execute_command tool call
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_exec_1",
                            "function": {
                                "name": "execute_command",
                                "arguments": json.dumps({"command": "python calc.py"}),
                            },
                        }],
                    }
                }]
            },
            # Step 3: Model produces final text response
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "The factorial of 5 is 120. Task complete.",
                    }
                }]
            },
        ]

        provider = make_mock_provider(mock_responses)
        engine = AutonomousAgentEngine(
            tools_instance=mock_tools,
            provider_fn=provider,
            store=store,
        )

        # Create task
        task_id = await engine.create_task(
            prompt="Create a factorial calculator and run it.",
            title="Factorial Calculator",
        )

        # Verify initial state
        record = store.get_task(task_id)
        assert record is not None
        assert record.status == TaskStatus.PENDING

        # Run to completion
        result = await engine.run_to_completion(task_id)

        # Verify outcome
        assert result.status == TaskStatus.COMPLETED
        assert result.total_steps == 3
        assert result.final_output == "The factorial of 5 is 120. Task complete."
        assert len(result.step_results) == 3

        # Verify step progression
        assert result.step_results[0].tool_calls_made == ["write_file"]
        assert result.step_results[1].tool_calls_made == ["execute_command"]
        assert result.step_results[2].tool_calls_made == []
        assert result.step_results[2].status == TaskStatus.COMPLETED

        # Verify file was actually written by mock tool
        assert (Path(tmp_dir) / "calc.py").exists()

        # Verify final state in DB
        final_record = store.get_task(task_id)
        assert final_record.status == TaskStatus.COMPLETED
        assert final_record.current_step == 3
        assert len(final_record.history) > 0


@pytest.mark.asyncio
async def test_engine_step_by_step():
    """
    Verify the step() method works correctly for individual steps,
    and that state is checkpointed to DB after each step.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_tools = MockTools(workspace_dir=tmp_dir)
        store = TaskStore(db_path=":memory:")

        mock_responses = [
            # Step 1: write_file
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_1",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({"path": "test.py", "content": "print('hi')"}),
                            },
                        }],
                    }
                }]
            },
            # Step 2: final text
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Done!",
                    }
                }]
            },
        ]

        provider = make_mock_provider(mock_responses)
        engine = AutonomousAgentEngine(
            tools_instance=mock_tools,
            provider_fn=provider,
            store=store,
        )

        task_id = await engine.create_task(prompt="Create test.py")

        # Step 1
        step1 = await engine.step(task_id)
        assert step1.step_number == 1
        assert step1.status == TaskStatus.RUNNING
        assert "write_file" in step1.tool_calls_made

        # Verify checkpoint
        record = store.get_task(task_id)
        assert record.current_step == 1
        assert record.status == TaskStatus.RUNNING

        # Step 2
        step2 = await engine.step(task_id)
        assert step2.step_number == 2
        assert step2.status == TaskStatus.COMPLETED
        assert step2.final_output == "Done!"

        # Verify final state
        record = store.get_task(task_id)
        assert record.current_step == 2
        assert record.status == TaskStatus.COMPLETED


# ─────────────────────────────────────────────────────────────────────────────
# 4. Autonomous Self-Healing Test (Mocked Provider)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_engine_self_healing():
    """
    Verify autonomous self-healing:
      Step 1: Model calls execute_command → fails (exit code 1, syntax error)
      Step 2: Engine injects error reflection → Model writes corrected file
      Step 3: Model calls execute_command again → succeeds
      Step 4: Model produces final text confirming fix

    Verify recovery.py formatted the error context into the next turn.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_tools = MockTools(workspace_dir=tmp_dir)

        # Configure the mock to return an error on the first execute_command
        call_count = {"execute_command": 0}
        original_execute = mock_tools.execute_command

        async def conditional_execute(command: str, **kwargs) -> str:
            call_count["execute_command"] += 1
            if call_count["execute_command"] == 1:
                # First call: return a failure receipt
                return json.dumps({
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "  File \"broken.py\", line 1\n    print(undefined_variable)\n          ^^^^^^^^^^^^^^^^^\nNameError: name 'undefined_variable' is not defined",
                    "command": command,
                })
            # Second call: success
            return json.dumps({
                "exit_code": 0,
                "stdout": "Hello, World!",
                "stderr": "",
                "command": command,
            })

        mock_tools.execute_command = conditional_execute

        store = TaskStore(db_path=":memory:")

        mock_responses = [
            # Step 1: Model tries to execute the broken script
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_exec_1",
                            "function": {
                                "name": "execute_command",
                                "arguments": json.dumps({"command": "python broken.py"}),
                            },
                        }],
                    }
                }]
            },
            # Step 2: After seeing the error reflection, model writes fix
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_write_fix",
                            "function": {
                                "name": "write_file",
                                "arguments": json.dumps({
                                    "path": "broken.py",
                                    "content": "print('Hello, World!')\n",
                                }),
                            },
                        }],
                    }
                }]
            },
            # Step 3: Model re-executes the fixed script
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_exec_2",
                            "function": {
                                "name": "execute_command",
                                "arguments": json.dumps({"command": "python broken.py"}),
                            },
                        }],
                    }
                }]
            },
            # Step 4: Model confirms success
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Fixed the script. It now prints 'Hello, World!' successfully.",
                    }
                }]
            },
        ]

        provider = make_mock_provider(mock_responses)
        engine = AutonomousAgentEngine(
            tools_instance=mock_tools,
            provider_fn=provider,
            store=store,
        )

        task_id = await engine.create_task(
            prompt="Run broken.py and fix any errors.",
        )

        result = await engine.run_to_completion(task_id)

        # ── Verify self-healing succeeded ────────────────────────────────
        assert result.status == TaskStatus.COMPLETED
        assert result.total_steps == 4

        # Step 1: executed broken command (failed)
        assert result.step_results[0].tool_calls_made == ["execute_command"]

        # Step 2: wrote the fix
        assert result.step_results[1].tool_calls_made == ["write_file"]

        # Step 3: re-executed (succeeded)
        assert result.step_results[2].tool_calls_made == ["execute_command"]

        # Step 4: final confirmation
        assert result.step_results[3].status == TaskStatus.COMPLETED
        assert "Hello, World!" in result.final_output

        # ── Verify error reflection was injected into history ────────────
        final_record = store.get_task(task_id)
        history = final_record.history

        # Find the tool result message after the first execute_command
        # It should contain the structured error reflection
        tool_results = [
            m for m in history
            if m.get("role") == "tool" and "Tool Execution Error" in m.get("content", "")
        ]
        assert len(tool_results) >= 1, "Error reflection must appear in conversation history"

        reflection_content = tool_results[0]["content"]
        assert "Exit Code: 1" in reflection_content
        assert "NameError" in reflection_content
        assert "corrective action" in reflection_content.lower()

        # Verify the fixed file was written
        fixed_file = Path(tmp_dir) / "broken.py"
        assert fixed_file.exists()
        assert "Hello, World!" in fixed_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_engine_provider_error_handling():
    """
    Verify that a provider exception (network error, API failure) sets the
    task to FAILED status rather than crashing the engine.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_tools = MockTools(workspace_dir=tmp_dir)
        store = TaskStore(db_path=":memory:")

        async def failing_provider(messages, tools):
            raise ConnectionError("Simulated network failure")

        engine = AutonomousAgentEngine(
            tools_instance=mock_tools,
            provider_fn=failing_provider,
            store=store,
        )

        task_id = await engine.create_task(prompt="This will fail")
        result = await engine.run_to_completion(task_id)

        assert result.status == TaskStatus.FAILED
        assert len(result.step_results) == 1
        assert result.step_results[0].error is not None
        assert "network failure" in result.step_results[0].error.lower()

        # Verify DB state
        record = store.get_task(task_id)
        assert record.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_engine_step_limit_pauses():
    """
    Verify that when step_limit is set, the task pauses at the limit
    instead of continuing indefinitely.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        mock_tools = MockTools(workspace_dir=tmp_dir)
        store = TaskStore(db_path=":memory:")

        # Provider always returns tool calls (would loop forever without limit)
        infinite_responses = [
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": f"call_{i}",
                            "function": {
                                "name": "list_files",
                                "arguments": json.dumps({"subpath": "."}),
                            },
                        }],
                    }
                }]
            }
            for i in range(10)
        ]

        provider = make_mock_provider(infinite_responses)
        engine = AutonomousAgentEngine(
            tools_instance=mock_tools,
            provider_fn=provider,
            store=store,
        )

        # Create task with step_limit=3
        record = store.create_task(prompt="Loop test", step_limit=3)
        # Initialize history
        store.update_task(
            record.task_id,
            history=[{"role": "user", "content": "Loop test"}],
        )

        result = await engine.run_to_completion(record.task_id)

        assert result.status == TaskStatus.PAUSED
        assert result.total_steps == 3

        # Verify DB state
        db_record = store.get_task(record.task_id)
        assert db_record.status == TaskStatus.PAUSED
        assert db_record.current_step == 3
