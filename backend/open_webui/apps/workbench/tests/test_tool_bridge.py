"""
Unit Tests for Workbench Tool Bridge & Open WebUI Integration
Test Module: backend.open_webui.apps.workbench.tests.test_tool_bridge
"""

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List
import pytest

# Ensure WEBUI_SECRET_KEY is present for any upstream Open WebUI imports
os.environ.setdefault("WEBUI_SECRET_KEY", "test-secret-key-for-tool-bridge-tests")

from open_webui.apps.workbench.tools.workspace_tools import Tools
from open_webui.utils.tools import get_tool_specs


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tool Schema Validation via Open WebUI parser
# ─────────────────────────────────────────────────────────────────────────────

def test_tool_schema_validation():
    """
    Verify Open WebUI's get_tool_specs introspects the Tools class and
    produces valid OpenAI-compatible function calling schemas.
    """
    tools = Tools()
    specs = get_tool_specs(tools)

    assert isinstance(specs, list), "Expected specs to be a list"
    assert len(specs) >= 4, f"Expected at least 4 tool specs, got {len(specs)}"

    spec_map = {spec["name"]: spec for spec in specs}

    expected_functions = ["list_files", "read_file", "write_file", "execute_command"]
    for func_name in expected_functions:
        assert func_name in spec_map, f"Function {func_name} missing from generated specs"
        spec = spec_map[func_name]
        assert "description" in spec and spec["description"], f"Missing description for {func_name}"
        assert "parameters" in spec, f"Missing parameters for {func_name}"
        assert spec["parameters"].get("type") == "object"
        assert "properties" in spec["parameters"]

        # Ensure internal __event_emitter__ is excluded from OpenAI parameters schema
        assert "__event_emitter__" not in spec["parameters"]["properties"]

    # Detailed parameter verification
    read_params = spec_map["read_file"]["parameters"]["properties"]
    assert "path" in read_params
    assert "max_bytes" in read_params
    assert "path" in spec_map["read_file"]["parameters"].get("required", [])

    write_params = spec_map["write_file"]["parameters"]["properties"]
    assert "path" in write_params
    assert "content" in write_params
    assert "path" in spec_map["write_file"]["parameters"].get("required", [])
    assert "content" in spec_map["write_file"]["parameters"].get("required", [])


# ─────────────────────────────────────────────────────────────────────────────
# 2. Safe Mode Enforcement
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safe_mode_enforcement():
    """
    Verify write_file and state-mutating commands are rejected when EXECUTION_MODE is SAFE.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "SAFE"

        # 1. write_file must be rejected under SAFE mode
        write_res = await tools.write_file("new_file.txt", "sample content")
        assert "Policy blocked write action" in write_res or "SAFE" in write_res
        assert not (Path(tmp_dir) / "new_file.txt").exists()

        # 2. Mutating command must be rejected under SAFE mode
        cmd_res = await tools.execute_command("git commit -m 'test commit'")
        assert "Policy blocked command execution" in cmd_res
        assert "SAFE" in cmd_res or "HIGH" in cmd_res

        # 3. Read and list actions must remain permitted in SAFE mode
        # Create a file directly on disk to test reading
        test_file = Path(tmp_dir) / "safe_read.txt"
        test_file.write_text("safe content to read", encoding="utf-8")

        read_res = await tools.read_file("safe_read.txt")
        assert read_res == "safe content to read"

        list_res = await tools.list_files(".")
        entries = json.loads(list_res)
        assert any(e["name"] == "safe_read.txt" for e in entries)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Path Traversal Block in Tools
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path_traversal_blocked_in_tools():
    """
    Verify attempting to escape the workspace via path traversal returns a clean
    security error without crashing.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "AUTONOMOUS"

        # 1. Read outside workspace
        read_res = await tools.read_file("../../outside.txt")
        assert "Security Error" in read_res or "escapes workspace" in read_res

        # 2. Write outside workspace
        write_res = await tools.write_file("../malicious.py", "print('hacked')")
        assert "Security Error" in write_res or "escapes workspace" in write_res

        # 3. Null byte injection
        null_res = await tools.read_file("file.txt\0.exe")
        assert "Security Error" in null_res or "Null bytes" in null_res


# ─────────────────────────────────────────────────────────────────────────────
# 4. Execution & Event Emission
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execution_and_event_emission():
    """
    Verify execute_command streams status events to mock __event_emitter__
    and correctly captures process execution stdout.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "AUTONOMOUS"
        tools.valves.TIMEOUT_SECONDS = 15

        emitted_events: List[Dict[str, Any]] = []

        async def mock_event_emitter(event: Dict[str, Any]):
            emitted_events.append(event)

        test_msg = "Workbench Event Stream Verification OK"
        py_cmd = f'"{sys.executable}" -c "print(\'{test_msg}\')"'

        res = await tools.execute_command(py_cmd, __event_emitter__=mock_event_emitter)

        # Verify output report
        assert "Exit Code: 0" in res
        assert test_msg in res

        # Verify events were streamed
        assert len(emitted_events) >= 2, f"Expected multiple events, got {len(emitted_events)}"
        descriptions = [e.get("data", {}).get("description", "") for e in emitted_events]
        assert any("Evaluating command" in d for d in descriptions)
        assert any("Command finished with exit code 0" in d for d in descriptions)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Permanently Forbidden Command Block
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forbidden_command_blocked():
    """
    Verify dangerous destructive or privileged commands are blocked unconditionally
    with CRITICAL risk level, even in AUTONOMOUS mode.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "AUTONOMOUS"

        forbidden_attempts = [
            "rm -rf /",
            "rm -rf /*",
            "rmdir /s /q C:\\",
            "format C:",
            "cat /etc/shadow",
            r"reg save HKLM\SAM sam.hive",
        ]

        for cmd in forbidden_attempts:
            res = await tools.execute_command(cmd)
            assert "Policy blocked command execution" in res, f"Expected policy block for '{cmd}', got: {res}"
            assert "CRITICAL" in res, f"Expected CRITICAL risk level for '{cmd}', got: {res}"


# ─────────────────────────────────────────────────────────────────────────────
# 6. End-to-End Workspace Operations (Write, List, Read)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_end_to_end_workspace_operations():
    """
    Verify sequential write, list, and read operations in AUTONOMOUS mode.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tools = Tools()
        tools.valves.WORKSPACE_ROOT = tmp_dir
        tools.valves.EXECUTION_MODE = "AUTONOMOUS"

        # Write
        content = "def add(a, b):\n    return a + b\n"
        write_res = await tools.write_file("src/math_utils.py", content)
        assert "Successfully wrote" in write_res

        # List
        list_res = await tools.list_files("src")
        entries = json.loads(list_res)
        assert len(entries) == 1
        assert entries[0]["name"] == "math_utils.py"

        # Read
        read_res = await tools.read_file("src/math_utils.py")
        assert read_res == content
