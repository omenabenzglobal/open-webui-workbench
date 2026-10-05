"""
Workbench Runtime Package
Module: backend.open_webui.apps.workbench.runtime

Provides the Durable Agent Runtime for multi-step autonomous task execution
with state persistence, step iteration, self-healing, and checkpointing.
"""

from open_webui.apps.workbench.runtime.schema import TaskRecord, TaskStatus, TaskStore
from open_webui.apps.workbench.runtime.engine import (
    AutonomousAgentEngine,
    TaskResult,
    TaskStepResult,
)
from open_webui.apps.workbench.runtime.recovery import format_error_reflection

__all__ = [
    "AutonomousAgentEngine",
    "TaskRecord",
    "TaskResult",
    "TaskStatus",
    "TaskStepResult",
    "TaskStore",
    "format_error_reflection",
]
