"""
Self-Healing & Reflection Hook
Module: backend.open_webui.apps.workbench.runtime.recovery

Transforms tool execution failures into structured diagnostic prompts that
guide the model toward self-correction.  The formatted messages are injected
into the conversation history so the model can analyse stdout, stderr,
tracebacks, and exit codes without manual intervention.

Design principles
~~~~~~~~~~~~~~~~~
- **Structured, not prescriptive:** Provides factual context (exit code,
  stderr, stdout) and a gentle nudge ("Analyze the failure above and take
  corrective action") without over-constraining the model's reasoning.
- **Truncation-safe:** Large stderr/stdout blobs are truncated to prevent
  context window exhaustion while preserving the most diagnostic content
  (tail of output is kept, head is trimmed).
- **Composable:** Returns plain strings suitable for insertion as ``role:
  tool`` content in the message history.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# Maximum characters of stdout/stderr to include in reflection prompts.
# Keeps the tail (most recent output) which is usually the most diagnostic.
MAX_OUTPUT_CHARS = 4000


def _truncate_tail(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the last ``max_chars`` characters, prepending a truncation notice."""
    if not text or len(text) <= max_chars:
        return text
    return f"[… truncated {len(text) - max_chars} chars …]\n{text[-max_chars:]}"


def format_error_reflection(
    tool_name: str,
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
    exception: Optional[str] = None,
    command: Optional[str] = None,
) -> str:
    """
    Build a structured error reflection prompt for the model.

    Parameters
    ----------
    tool_name : str
        Name of the tool that failed (e.g. ``execute_command``, ``write_file``).
    exit_code : int
        Process exit code (non-zero indicates failure).
    stdout : str
        Standard output captured from the failed execution.
    stderr : str
        Standard error captured from the failed execution.
    exception : str, optional
        Python exception traceback if the failure was an internal error.
    command : str, optional
        The command string that was executed (for context).

    Returns
    -------
    str
        A structured diagnostic message ready for insertion into the
        conversation history as tool result content.
    """
    lines = [
        f"⚠ Tool Execution Error",
        f"  Tool:      {tool_name}",
        f"  Exit Code: {exit_code}",
    ]

    if command:
        lines.append(f"  Command:   {command}")

    if stdout and stdout.strip():
        lines.append(f"\n── stdout ({'truncated' if len(stdout) > MAX_OUTPUT_CHARS else 'complete'}) ──")
        lines.append(_truncate_tail(stdout.strip()))

    if stderr and stderr.strip():
        lines.append(f"\n── stderr ({'truncated' if len(stderr) > MAX_OUTPUT_CHARS else 'complete'}) ──")
        lines.append(_truncate_tail(stderr.strip()))

    if exception:
        lines.append(f"\n── exception ──")
        lines.append(_truncate_tail(exception.strip()))

    lines.append("")
    lines.append(
        "Analyze the failure above and take corrective action. "
        "If the error is in source code, fix the file and retry. "
        "If a dependency is missing, install it. "
        "If the command is wrong, correct it."
    )

    return "\n".join(lines)


def format_tool_result(
    tool_name: str,
    raw_result: str,
    is_error: bool = False,
) -> str:
    """
    Normalize a tool result string for inclusion in message history.

    For successful results, returns the raw result as-is (truncated if huge).
    For error results, wraps in the structured error format.

    Parameters
    ----------
    tool_name : str
        Name of the tool that produced this result.
    raw_result : str
        The raw output string from the tool.
    is_error : bool
        Whether this result represents an error condition.

    Returns
    -------
    str
        Normalized result string.
    """
    if not is_error:
        return _truncate_tail(raw_result, MAX_OUTPUT_CHARS * 2)

    # For error results, try to parse structured receipt format
    # Our workspace_tools return JSON receipts for command execution
    return raw_result


def extract_error_from_receipt(receipt_json: str) -> Optional[Dict[str, Any]]:
    """
    Parse a tool receipt JSON string and extract error fields if present.

    Returns a dict with keys ``exit_code``, ``stdout``, ``stderr`` if the
    receipt indicates failure, or ``None`` if the execution succeeded.
    """
    import json
    try:
        receipt = json.loads(receipt_json)
    except (json.JSONDecodeError, TypeError):
        return None

    # Only dict receipts can contain structured error fields
    if not isinstance(receipt, dict):
        return None

    # Check for our CommandResult JSON format
    exit_code = receipt.get("exit_code")
    if exit_code is not None and exit_code != 0:
        return {
            "exit_code": exit_code,
            "stdout": receipt.get("stdout", ""),
            "stderr": receipt.get("stderr", ""),
            "command": receipt.get("command", ""),
        }

    # Check for string error indicators
    if isinstance(receipt, str) and receipt.startswith("Error:"):
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": receipt,
            "command": "",
        }

    return None
