"""
Unit & Integration Test Suite: Workbench API Router
Test Module: backend.open_webui.apps.workbench.tests.test_api
Directive: DIR-5.1-WORKBENCH-API-AND-UI-SHELL
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure WEBUI_SECRET_KEY is present
os.environ.setdefault("WEBUI_SECRET_KEY", "test-secret-key-for-api-tests")

from open_webui.apps.workbench.api import router as workbench_router, workspace_boundary, task_store


@pytest.fixture
def client():
    """Provides a TestClient mounted with the workbench router."""
    app = FastAPI()
    app.include_router(workbench_router, prefix="/api/v1/workbench")
    return TestClient(app)


def test_api_status(client):
    """Verify /status endpoint returns health, execution mode, and metadata."""
    resp = client.get("/api/v1/workbench/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["execution_mode"] == "AUTONOMOUS"
    assert "workspace_root" in data
    assert "timestamp" in data


def test_api_workspace_tree(client):
    """Verify /workspace/tree returns recursive directory structure."""
    resp = client.get("/api/v1/workbench/workspace/tree")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "path" in data
    assert data["is_dir"] is True
    assert isinstance(data.get("children"), list)


def test_api_workspace_file_lifecycle(client):
    """Verify writing, reading, and boundary checking via API."""
    test_rel_path = "test_dir/api_test_file.txt"
    test_content = "Hello from Workbench API test!"

    # 1. Write file
    write_resp = client.post(
        "/api/v1/workbench/workspace/file",
        json={"path": test_rel_path, "content": test_content},
    )
    assert write_resp.status_code == 200
    write_data = write_resp.json()
    assert write_data["status"] == "ok"
    assert write_data["path"] == test_rel_path
    assert write_data["bytes_written"] == len(test_content.encode("utf-8"))

    # 2. Read file
    read_resp = client.get(f"/api/v1/workbench/workspace/file?path={test_rel_path}")
    assert read_resp.status_code == 200
    read_data = read_resp.json()
    assert read_data["path"] == test_rel_path
    assert read_data["content"] == test_content
    assert read_data["size"] == len(test_content.encode("utf-8"))

    # 3. Path traversal rejection
    traversal_resp = client.get("/api/v1/workbench/workspace/file?path=../../outside.txt")
    assert traversal_resp.status_code in (403, 404)

    # Clean up test file
    try:
        workspace_boundary.delete_file(test_rel_path)
    except Exception:
        pass


def test_api_terminal_exec(client):
    """Verify /terminal/exec runs sandboxed commands and returns execution receipts."""
    # Execute a safe python one-liner
    exec_resp = client.post(
        "/api/v1/workbench/terminal/exec",
        json={"command": "python -c \"print('workbench_api_terminal_ok')\"", "timeout": 15},
    )
    assert exec_resp.status_code == 200
    data = exec_resp.json()
    assert data["exit_code"] == 0
    assert "workbench_api_terminal_ok" in data["stdout"]
    assert data["timed_out"] is False
    assert data["duration_ms"] >= 0


def test_api_terminal_exec_forbidden_command(client):
    """Verify /terminal/exec blocks permanently forbidden destructive commands."""
    exec_resp = client.post(
        "/api/v1/workbench/terminal/exec",
        json={"command": "rm -rf /", "timeout": 5},
    )
    assert exec_resp.status_code == 403
    assert "blocked" in exec_resp.json()["detail"].lower()


def test_api_tasks_lifecycle(client):
    """Verify task creation, details retrieval, and run scheduling."""
    # 1. Create task
    create_resp = client.post(
        "/api/v1/workbench/tasks/create",
        json={
            "prompt": "Create an automated test script and verify it.",
            "title": "API Test Task",
            "step_limit": 5,
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()
    assert "task_id" in create_data
    task_id = create_data["task_id"]
    assert create_data["title"] == "API Test Task"
    assert create_data["status"] == "PENDING"

    # 2. Get task details
    detail_resp = client.get(f"/api/v1/workbench/tasks/{task_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["task_id"] == task_id
    assert detail_data["prompt"] == "Create an automated test script and verify it."
    assert isinstance(detail_data.get("history"), list)

    # 3. Schedule task run
    run_resp = client.post(f"/api/v1/workbench/tasks/{task_id}/run")
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "RUNNING"


def test_main_app_mount():
    """Verify that open_webui.main.app mounts the /api/v1/workbench router cleanly."""
    from open_webui.main import app
    route_paths = [r.path for r in app.routes]
    assert any("/api/v1/workbench" in p for p in route_paths), (
        f"Workbench router not found in main app routes: {route_paths[:20]}"
    )
