"""
Unit Tests for Workbench Security Boundaries and Execution Policies
Test Module: backend.open_webui.apps.workbench.tests.test_security
"""

import os
from pathlib import Path
import sys
import tempfile
import pytest

from open_webui.apps.workbench.security.exceptions import (
    PathTraversalError,
    SecurityException,
)
from open_webui.apps.workbench.security.executor import SafeExecutor
from open_webui.apps.workbench.security.policy import (
    ExecutionMode,
    PolicyEngine,
    PolicyStatus,
    RiskLevel,
)
from open_webui.apps.workbench.security.workspace import WorkspaceBoundary


# ─────────────────────────────────────────────────────────────────────────────
# 1. Path Traversal & Boundary Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_workspace_path_traversal_rejection():
    """Verify that path traversal attempts escaping the workspace are blocked."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        boundary = WorkspaceBoundary(tmp_dir)

        # Relative escapes
        with pytest.raises(SecurityException):
            boundary.resolve_path("../../etc/passwd")

        with pytest.raises(SecurityException):
            boundary.resolve_path(r"..\..\Windows\System32")

        with pytest.raises(SecurityException):
            boundary.resolve_path("subfolder/../../../../escape.txt")

        # Absolute paths outside workspace
        outside_abs = Path(tmp_dir).parent / "outside_file.txt"
        with pytest.raises(SecurityException):
            boundary.resolve_path(str(outside_abs))

        # Null byte injection
        with pytest.raises(SecurityException):
            boundary.resolve_path("file.txt\0.exe")


def test_workspace_safe_confinement_operations():
    """Verify safe read, write, list, and delete operations inside the workspace."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        boundary = WorkspaceBoundary(tmp_dir)
        boundary.ensure_workspace()

        # 1. Write file inside workspace
        bytes_written = boundary.write_file("src/main.py", "print('hello workbench')")
        assert bytes_written > 0

        # 2. Read file
        content = boundary.read_file("src/main.py")
        assert content == "print('hello workbench')"

        # 3. List directory
        entries = boundary.list_dir("src")
        assert len(entries) == 1
        assert entries[0]["name"] == "main.py"
        assert entries[0]["is_dir"] is False

        # 4. Attempt to write outside workspace
        with pytest.raises(SecurityException):
            boundary.write_file("../outside.py", "malicious_content")

        # 5. Delete file
        deleted = boundary.delete_file("src/main.py")
        assert deleted is True
        assert not (Path(tmp_dir) / "src" / "main.py").exists()

        # 6. Cannot delete root directory
        with pytest.raises(SecurityException):
            boundary.delete_file("")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Policy Engine Decisions (SAFE, ASSISTED, AUTONOMOUS)
# ─────────────────────────────────────────────────────────────────────────────

def test_policy_engine_read_only_actions():
    """Read-only actions must be permitted across all modes."""
    engine = PolicyEngine()
    read_cmds = [
        "ls -la",
        "dir /w",
        "cat README.md",
        "git status",
        "git diff HEAD~1",
        "python --version",
        "where.exe node",
    ]

    for cmd in read_cmds:
        for mode in (ExecutionMode.SAFE, ExecutionMode.ASSISTED, ExecutionMode.AUTONOMOUS):
            decision = engine.evaluate_action(mode=mode, action_type="execute", command_or_path=cmd)
            assert decision.is_allowed, f"Expected {cmd} to be allowed in {mode}, got {decision.status}"
            assert decision.risk_level == RiskLevel.LOW


def test_policy_engine_state_mutating_actions():
    """State-mutating actions must be blocked in SAFE, require confirmation in ASSISTED, and pass in AUTONOMOUS."""
    engine = PolicyEngine()
    mutating_cmds = [
        "git commit -m 'feat: add feature'",
        "npm run build",
        "pytest backend/tests",
        "python script.py",
        "mkdir build_output",
    ]

    for cmd in mutating_cmds:
        # SAFE mode: strictly BLOCKED
        d_safe = engine.evaluate_action(mode=ExecutionMode.SAFE, action_type="execute", command_or_path=cmd)
        assert d_safe.is_blocked, f"Expected {cmd} to be BLOCKED in SAFE, got {d_safe.status}"
        assert d_safe.risk_level == RiskLevel.HIGH

        # ASSISTED mode: CONFIRMATION_REQUIRED
        d_assisted = engine.evaluate_action(mode=ExecutionMode.ASSISTED, action_type="execute", command_or_path=cmd)
        assert d_assisted.requires_confirmation, f"Expected {cmd} to require confirmation in ASSISTED, got {d_assisted.status}"
        assert d_assisted.risk_level == RiskLevel.MEDIUM

        # AUTONOMOUS mode: ALLOWED
        d_auto = engine.evaluate_action(mode=ExecutionMode.AUTONOMOUS, action_type="execute", command_or_path=cmd)
        assert d_auto.is_allowed, f"Expected {cmd} to be ALLOWED in AUTONOMOUS, got {d_auto.status}"
        assert d_auto.risk_level == RiskLevel.MEDIUM


def test_policy_engine_permanently_forbidden():
    """Destructive or privileged commands must be permanently blocked in all modes."""
    engine = PolicyEngine()
    forbidden_cmds = [
        "rm -rf /",
        "rm -rf /*",
        "rmdir /s /q C:\\",
        "format C:",
        "shutdown -h now",
        "cat /etc/shadow",
        r"reg save HKLM\SAM sam.hive",
    ]

    for cmd in forbidden_cmds:
        for mode in (ExecutionMode.SAFE, ExecutionMode.ASSISTED, ExecutionMode.AUTONOMOUS):
            decision = engine.evaluate_action(mode=mode, action_type="execute", command_or_path=cmd)
            assert decision.is_blocked, f"Expected forbidden command '{cmd}' to be BLOCKED in {mode}, got {decision.status}"
            assert decision.risk_level == RiskLevel.CRITICAL


# ─────────────────────────────────────────────────────────────────────────────
# 3. Subprocess Execution, Timeout & Truncation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safe_executor_command_success():
    """Verify normal command execution and output capture."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = SafeExecutor(default_timeout_seconds=10)
        cmd = [sys.executable, "-c", "print('Workbench Subprocess OK')"]

        result = await executor.run_command(cmd, cwd=Path(tmp_dir))
        assert result.is_success
        assert result.exit_code == 0
        assert "Workbench Subprocess OK" in result.stdout
        assert result.timed_out is False
        assert result.truncated is False


@pytest.mark.asyncio
async def test_safe_executor_timeout_enforcement():
    """Verify that a hung or long-running command is killed upon timeout."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = SafeExecutor()
        # Sleep for 10 seconds with a 1 second timeout deadline
        cmd = [sys.executable, "-c", "import time; time.sleep(10)"]

        result = await executor.run_command(cmd, cwd=Path(tmp_dir), timeout_seconds=1)
        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timed out after 1 seconds" in result.stderr
        assert result.duration_seconds >= 0.9


@pytest.mark.asyncio
async def test_safe_executor_output_truncation():
    """Verify that output exceeding max_output_bytes is safely truncated."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        executor = SafeExecutor()
        # Generate 10,000 characters of stdout, with a 500 byte limit
        cmd = [sys.executable, "-c", "print('X' * 10000)"]

        result = await executor.run_command(cmd, cwd=Path(tmp_dir), max_output_bytes=500)
        assert result.is_success
        assert result.truncated is True
        assert "[TRUNCATED - EXCEEDED 500 BYTES]" in result.stdout
        # Output should be roughly 500 bytes plus the truncation notice
        assert len(result.stdout) < 1000


@pytest.mark.asyncio
async def test_safe_executor_environment_sanitization():
    """Verify that sensitive environment variables are stripped from subprocesses."""
    # Inject dummy sensitive environment variables
    os.environ["OPENAI_API_KEY"] = "sk-test-secret-12345"
    os.environ["WEBUI_SECRET_KEY"] = "webui-jwt-secret-67890"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "aws-secret-test"

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            executor = SafeExecutor()
            cmd = [
                sys.executable,
                "-c",
                "import os; print('KEY_CHECK:' + os.environ.get('OPENAI_API_KEY', 'CLEAN'))",
            ]

            result = await executor.run_command(cmd, cwd=Path(tmp_dir))
            assert result.is_success
            assert "KEY_CHECK:CLEAN" in result.stdout
            assert "sk-test-secret-12345" not in result.stdout

    finally:
        # Clean up dummy test variables
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("WEBUI_SECRET_KEY", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
