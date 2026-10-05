"""
Autonomous Agent Execution Engine
Module: backend.open_webui.apps.workbench.runtime.engine

Implements the core execution state machine that drives multi-step autonomous
task completion.  The engine iterates a model ↔ tool loop: it sends the
current conversation history (including all prior tool receipts) to the LLM,
dispatches any emitted tool calls through ``workspace_tools.py``, appends
results back to history, checkpoints state to SQLite, and repeats until the
model produces a final text response or an unrecoverable failure occurs.

Design decisions
~~~~~~~~~~~~~~~~
- **Provider-agnostic callable:** The engine accepts a ``provider_fn`` async
  callable ``(messages, tools) → response_dict`` instead of binding to a
  specific HTTP client.  This makes it testable with mock providers and
  compatible with any OpenAI-compatible endpoint.
- **No artificial step limits on autonomous runs:** ``step_limit=0`` means
  truly unlimited.  ``run_to_completion`` accepts a ``max_iterations``
  safety guard (default 50) that is distinct from the task-level step_limit
  and serves only as a runaway protection, not a policy restriction.
- **Self-healing via recovery module:** When a tool returns an error receipt,
  the engine injects a structured diagnostic prompt from ``recovery.py``
  to guide model self-correction.
- **Checkpoint-on-every-step:** After each tool dispatch cycle, the full
  conversation history and step counter are persisted to SQLite so the task
  can survive process restarts.
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from open_webui.apps.workbench.runtime.recovery import (
    extract_error_from_receipt,
    format_error_reflection,
)
from open_webui.apps.workbench.runtime.schema import (
    TaskRecord,
    TaskStatus,
    TaskStore,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskStepResult:
    """Outcome of a single engine step."""
    task_id: str
    step_number: int
    status: TaskStatus
    tool_calls_made: List[str] = field(default_factory=list)
    tool_results: List[str] = field(default_factory=list)
    final_output: Optional[str] = None
    error: Optional[str] = None


@dataclass
class TaskResult:
    """Outcome of a completed ``run_to_completion`` execution."""
    task_id: str
    status: TaskStatus
    total_steps: int
    final_output: Optional[str] = None
    error: Optional[str] = None
    step_results: List[TaskStepResult] = field(default_factory=list)


# Type alias for the provider function
# Signature: async (messages: List[Dict], tools: List[Dict]) -> Dict
ProviderFn = Callable[
    [List[Dict[str, Any]], List[Dict[str, Any]]],
    Coroutine[Any, Any, Dict[str, Any]],
]

# Type alias for the event emitter
EventEmitterFn = Callable[[Dict[str, Any]], Any]


# ─────────────────────────────────────────────────────────────────────────────
# Autonomous Agent Engine
# ─────────────────────────────────────────────────────────────────────────────

class AutonomousAgentEngine:
    """
    Stateful execution engine for autonomous multi-step tasks.

    Parameters
    ----------
    tools_instance : object
        An instance of ``workspace_tools.Tools`` (or compatible) that provides
        ``read_file``, ``write_file``, ``list_files``, ``execute_command``
        async methods.
    provider_fn : ProviderFn
        Async callable that sends messages + tool specs to the LLM and returns
        the OpenAI-compatible response dict.  Signature::

            async def provider_fn(
                messages: List[Dict[str, Any]],
                tools: List[Dict[str, Any]],
            ) -> Dict[str, Any]

    store : TaskStore, optional
        Persistent task store.  An in-memory store is created if not provided.
    event_emitter : EventEmitterFn, optional
        Callback for real-time progress updates (Open WebUI ``__event_emitter__``).
    """

    def __init__(
        self,
        tools_instance: Any,
        provider_fn: ProviderFn,
        store: Optional[TaskStore] = None,
        event_emitter: Optional[EventEmitterFn] = None,
    ):
        self.tools = tools_instance
        self.provider_fn = provider_fn
        self.store = store or TaskStore(db_path=":memory:")
        self.event_emitter = event_emitter

        # Build OpenAI-format tool specs from the tools instance
        self._tool_specs = self._build_tool_specs()

    def _build_tool_specs(self) -> List[Dict[str, Any]]:
        """
        Generate OpenAI function-calling tool specs from the tools instance.

        Attempts to use Open WebUI's ``get_tool_specs`` if available, falling
        back to manual introspection for test environments.
        """
        try:
            from open_webui.utils.tools import get_tool_specs
            specs = get_tool_specs(self.tools)
            return [
                {
                    "type": "function",
                    "function": {
                        "name": s["name"],
                        "description": s["description"],
                        "parameters": s["parameters"],
                    },
                }
                for s in specs
            ]
        except ImportError:
            log.warning("get_tool_specs not available, using empty tool list")
            return []

    async def _emit(self, description: str, done: bool = False) -> None:
        """Send a status event if an emitter is attached."""
        if not self.event_emitter:
            return
        payload = {
            "type": "status",
            "data": {"description": description, "done": done},
        }
        try:
            result = self.event_emitter(payload)
            if inspect.isawaitable(result):
                await result
        except Exception:
            pass  # Event emission must never crash the engine

    # ── Task Lifecycle ───────────────────────────────────────────────────

    async def create_task(
        self,
        prompt: str,
        title: str = "",
        step_limit: int = 0,
    ) -> str:
        """
        Initialize and persist a new autonomous task.

        Parameters
        ----------
        prompt : str
            The objective / instruction for the agent.
        title : str, optional
            Human-readable task title.
        step_limit : int, optional
            Maximum steps (0 = unlimited autonomous execution).

        Returns
        -------
        str
            The generated task_id.
        """
        record = self.store.create_task(
            prompt=prompt,
            title=title,
            step_limit=step_limit,
        )

        # Initialize history with the user prompt
        initial_history = [{"role": "user", "content": prompt}]
        self.store.update_task(
            record.task_id,
            history=initial_history,
            status=TaskStatus.PENDING,
        )

        await self._emit(f"Task created: {record.title}")
        log.info("Created task %s: %s", record.task_id, record.title)
        return record.task_id

    async def step(self, task_id: str) -> TaskStepResult:
        """
        Execute a single step of the autonomous loop.

        1. Load task state and conversation history from DB.
        2. Invoke model with current history and tool definitions.
        3. If model emits text without tools → mark COMPLETED, return output.
        4. If model emits tool_calls → dispatch each, append results to
           history, checkpoint to DB, return step summary.

        Returns
        -------
        TaskStepResult
            Summary of what happened in this step.

        Raises
        ------
        ValueError
            If the task_id doesn't exist.
        RuntimeError
            If the task is in a terminal state (COMPLETED/FAILED).
        """
        record = self.store.get_task(task_id)
        if record is None:
            raise ValueError(f"Task not found: {task_id}")

        if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            raise RuntimeError(
                f"Task {task_id} is in terminal state {record.status.value}"
            )

        # Transition to RUNNING on first step
        if record.status == TaskStatus.PENDING:
            self.store.update_task(task_id, status=TaskStatus.RUNNING)
            record.status = TaskStatus.RUNNING

        step_num = record.current_step + 1
        await self._emit(f"Step {step_num}: Invoking model…")

        # ── Invoke the LLM ──────────────────────────────────────────────
        try:
            response = await self.provider_fn(record.history, self._tool_specs)
        except Exception as e:
            error_msg = f"Provider error at step {step_num}: {type(e).__name__}: {e}"
            log.error(error_msg)
            self.store.update_task(
                task_id,
                status=TaskStatus.FAILED,
                current_step=step_num,
            )
            await self._emit(error_msg, done=True)
            return TaskStepResult(
                task_id=task_id,
                step_number=step_num,
                status=TaskStatus.FAILED,
                error=error_msg,
            )

        # ── Parse model response ────────────────────────────────────────
        try:
            msg = response["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            error_msg = f"Malformed provider response at step {step_num}: {e}"
            log.error(error_msg)
            self.store.update_task(
                task_id,
                status=TaskStatus.FAILED,
                current_step=step_num,
            )
            return TaskStepResult(
                task_id=task_id,
                step_number=step_num,
                status=TaskStatus.FAILED,
                error=error_msg,
            )

        # Append the assistant message to history
        history = list(record.history)
        history.append(msg)

        tool_calls = msg.get("tool_calls")

        # ── No tool calls → task completed ──────────────────────────────
        if not tool_calls:
            final_output = msg.get("content", "")
            self.store.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                current_step=step_num,
                history=history,
            )
            await self._emit(f"Task completed at step {step_num}", done=True)
            log.info("Task %s completed at step %d", task_id, step_num)
            return TaskStepResult(
                task_id=task_id,
                step_number=step_num,
                status=TaskStatus.COMPLETED,
                final_output=final_output,
            )

        # ── Dispatch tool calls ─────────────────────────────────────────
        tools_called: List[str] = []
        tool_results: List[str] = []

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, TypeError):
                args = {}
            tc_id = tc.get("id", f"call_{fn_name}_{step_num}")

            tools_called.append(fn_name)
            await self._emit(f"Step {step_num}: Executing {fn_name}…")

            # Dispatch to the appropriate tool method
            result_str = await self._dispatch_tool(fn_name, args)
            tool_results.append(result_str)

            # Check if the result indicates an error and enrich with
            # self-healing reflection
            error_info = extract_error_from_receipt(result_str)
            if error_info:
                reflection = format_error_reflection(
                    tool_name=fn_name,
                    exit_code=error_info["exit_code"],
                    stdout=error_info.get("stdout", ""),
                    stderr=error_info.get("stderr", ""),
                    command=error_info.get("command", ""),
                )
                # Use the reflection as the tool result content so the model
                # sees the structured diagnostic
                result_str = reflection

            history.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result_str,
            })

        # ── Check step limit ────────────────────────────────────────────
        new_status = TaskStatus.RUNNING
        if record.step_limit > 0 and step_num >= record.step_limit:
            new_status = TaskStatus.PAUSED
            await self._emit(
                f"Step limit ({record.step_limit}) reached. Task paused.",
                done=True,
            )

        # ── Checkpoint state ────────────────────────────────────────────
        self.store.update_task(
            task_id,
            status=new_status,
            current_step=step_num,
            history=history,
        )

        await self._emit(
            f"Step {step_num} complete: {', '.join(tools_called)}",
            done=(new_status != TaskStatus.RUNNING),
        )

        return TaskStepResult(
            task_id=task_id,
            step_number=step_num,
            status=new_status,
            tool_calls_made=tools_called,
            tool_results=tool_results,
        )

    async def run_to_completion(
        self,
        task_id: str,
        max_iterations: int = 50,
    ) -> TaskResult:
        """
        Loop ``step()`` continuously until the task reaches a terminal state.

        This is the main entry point for autonomous execution.  When
        ``step_limit=0`` (the default), the engine runs without pausing for
        manual confirmation — the model drives the loop until it produces a
        final text response or exhausts ``max_iterations`` (a safety guard,
        not a policy restriction).

        Parameters
        ----------
        task_id : str
            ID of the task to execute.
        max_iterations : int, optional
            Safety ceiling to prevent runaway loops.  Default 50.  This is
            NOT an artificial step limit — it exists solely to protect against
            infinite loops in case the model never produces a final response.

        Returns
        -------
        TaskResult
            Complete execution outcome with all step results.
        """
        step_results: List[TaskStepResult] = []
        final_output: Optional[str] = None
        final_status = TaskStatus.RUNNING
        total_steps = 0

        for iteration in range(max_iterations):
            try:
                step_result = await self.step(task_id)
            except (ValueError, RuntimeError) as e:
                # Task not found or already terminal
                final_status = TaskStatus.FAILED
                break

            step_results.append(step_result)
            total_steps = step_result.step_number

            if step_result.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.PAUSED,
            ):
                final_status = step_result.status
                final_output = step_result.final_output
                break

        else:
            # max_iterations exhausted without completion
            log.warning(
                "Task %s hit max_iterations (%d) safety guard",
                task_id,
                max_iterations,
            )
            self.store.update_task(task_id, status=TaskStatus.PAUSED)
            final_status = TaskStatus.PAUSED
            await self._emit(
                f"Safety guard: {max_iterations} iterations reached. Task paused.",
                done=True,
            )

        return TaskResult(
            task_id=task_id,
            status=final_status,
            total_steps=total_steps,
            final_output=final_output,
            step_results=step_results,
        )

    # ── Tool Dispatch ────────────────────────────────────────────────────

    async def _dispatch_tool(
        self,
        fn_name: str,
        args: Dict[str, Any],
    ) -> str:
        """
        Route a tool call to the appropriate method on ``self.tools``.

        Returns the string result from the tool, or an error message if
        the tool is unknown or raises an exception.
        """
        tool_method = getattr(self.tools, fn_name, None)
        if tool_method is None:
            return f"Error: Unknown tool '{fn_name}'"

        try:
            if inspect.iscoroutinefunction(tool_method):
                result = await tool_method(**args)
            else:
                result = tool_method(**args)
                if inspect.isawaitable(result):
                    result = await result
            return str(result)
        except Exception as e:
            error_msg = format_error_reflection(
                tool_name=fn_name,
                exit_code=1,
                stderr=str(e),
                exception=f"{type(e).__name__}: {e}",
            )
            log.warning("Tool %s raised: %s", fn_name, e)
            return error_msg

    # ── Task Query ───────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve current task state from the store."""
        return self.store.get_task(task_id)
