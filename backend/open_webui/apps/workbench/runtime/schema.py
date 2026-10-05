"""
Task State Database Schema & Store
Module: backend.open_webui.apps.workbench.runtime.schema

Defines the ``workbench_tasks`` table and a thread-safe ``TaskStore`` that
persists autonomous task state in an isolated SQLite database within the
workbench data directory.

Design decisions
~~~~~~~~~~~~~~~~
- Uses a **separate** SQLite database (``workbench_tasks.db``) rather than
  injecting tables into Open WebUI's main database.  This honours the "zero
  upstream modifications" constraint and keeps workbench state fully portable.
- Schema is self-initializing: ``TaskStore.__init__`` calls ``CREATE TABLE IF
  NOT EXISTS`` so no migration tooling is needed.
- JSON serialization of message history uses Python ``json`` module directly
  (no ORM JSON column), giving full control over encoding/decoding and
  avoiding SQLAlchemy version-specific JSON dialect differences.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Task Status Enumeration
# ─────────────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    """Lifecycle states for an autonomous task."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PAUSED = "PAUSED"


# ─────────────────────────────────────────────────────────────────────────────
# Task Record Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TaskRecord:
    """In-memory representation of a persisted task row."""
    task_id: str
    title: str
    status: TaskStatus
    prompt: str
    current_step: int
    step_limit: int
    history: List[Dict[str, Any]]
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (for JSON/API output)."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status.value,
            "prompt": self.prompt,
            "current_step": self.current_step,
            "step_limit": self.step_limit,
            "history_length": len(self.history),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Task Store (SQLite persistence)
# ─────────────────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workbench_tasks (
    task_id       TEXT PRIMARY KEY,
    title         TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'PENDING',
    prompt        TEXT NOT NULL DEFAULT '',
    current_step  INTEGER NOT NULL DEFAULT 0,
    step_limit    INTEGER NOT NULL DEFAULT 0,
    history_json  TEXT NOT NULL DEFAULT '[]',
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
"""


class TaskStore:
    """
    Thread-safe SQLite-backed store for autonomous task records.

    Each ``TaskStore`` instance manages a single persistent connection to an
    isolated SQLite database file.  The table is auto-created on first access.

    Parameters
    ----------
    db_path : str or Path, optional
        Filesystem path for the SQLite database.  Defaults to
        ``workbench_tasks.db`` in the current working directory.  Use
        ``":memory:"`` for ephemeral in-memory databases (tests).
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(os.getcwd(), "workbench_tasks.db")
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn = self._create_connection()
        self._ensure_table()

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            timeout=30.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @property
    def _db(self) -> sqlite3.Connection:
        """Return the persistent connection."""
        return self._conn

    def _ensure_table(self) -> None:
        with self._lock:
            self._db.execute(_CREATE_TABLE_SQL)
            self._db.commit()

    # ── CRUD Operations ──────────────────────────────────────────────────

    def create_task(
        self,
        prompt: str,
        title: str = "",
        step_limit: int = 0,
        task_id: Optional[str] = None,
    ) -> TaskRecord:
        """
        Insert a new task record and return it.

        Parameters
        ----------
        prompt : str
            The original objective / instruction for the autonomous agent.
        title : str, optional
            Short human-readable title.  Auto-generated from prompt if empty.
        step_limit : int, optional
            Maximum step count (0 = unlimited / truly autonomous).
        task_id : str, optional
            Explicit task ID.  A UUID4 is generated if not supplied.
        """
        if not task_id:
            task_id = str(uuid.uuid4())
        if not title:
            title = prompt[:80].strip() + ("…" if len(prompt) > 80 else "")
        now = time.time()
        history: List[Dict[str, Any]] = []

        with self._lock:
            self._db.execute(
                """
                INSERT INTO workbench_tasks
                    (task_id, title, status, prompt, current_step, step_limit,
                     history_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    TaskStatus.PENDING.value,
                    prompt,
                    0,
                    step_limit,
                    json.dumps(history),
                    now,
                    now,
                ),
            )
            self._db.commit()

        return TaskRecord(
            task_id=task_id,
            title=title,
            status=TaskStatus.PENDING,
            prompt=prompt,
            current_step=0,
            step_limit=step_limit,
            history=history,
            created_at=now,
            updated_at=now,
        )

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Load a task record by ID, or ``None`` if not found."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM workbench_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def update_task(
        self,
        task_id: str,
        *,
        status: Optional[TaskStatus] = None,
        current_step: Optional[int] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        title: Optional[str] = None,
    ) -> Optional[TaskRecord]:
        """
        Partially update a task record.  Only provided fields are changed.
        Returns the updated record, or ``None`` if the task doesn't exist.
        """
        # Build dynamic SET clause
        updates: List[str] = []
        params: List[Any] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if current_step is not None:
            updates.append("current_step = ?")
            params.append(current_step)
        if history is not None:
            updates.append("history_json = ?")
            params.append(json.dumps(history))
        if title is not None:
            updates.append("title = ?")
            params.append(title)

        if not updates:
            return self.get_task(task_id)

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(task_id)

        with self._lock:
            self._db.execute(
                f"UPDATE workbench_tasks SET {', '.join(updates)} WHERE task_id = ?",
                params,
            )
            self._db.commit()
        return self.get_task(task_id)

    def list_tasks(
        self,
        status_filter: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[TaskRecord]:
        """List tasks, optionally filtered by status, ordered by most recent."""
        with self._lock:
            if status_filter:
                rows = self._db.execute(
                    "SELECT * FROM workbench_tasks WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (status_filter.value, limit),
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM workbench_tasks ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def delete_task(self, task_id: str) -> bool:
        """Delete a task record.  Returns True if a row was deleted."""
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM workbench_tasks WHERE task_id = ?",
                (task_id,),
            )
            self._db.commit()
            return cursor.rowcount > 0

    # ── Internal Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> TaskRecord:
        """Convert a sqlite3.Row into a TaskRecord dataclass."""
        history_raw = row["history_json"]
        try:
            history = json.loads(history_raw) if history_raw else []
        except (json.JSONDecodeError, TypeError):
            log.warning("Corrupted history_json for task %s, resetting", row["task_id"])
            history = []

        return TaskRecord(
            task_id=row["task_id"],
            title=row["title"],
            status=TaskStatus(row["status"]),
            prompt=row["prompt"],
            current_step=row["current_step"],
            step_limit=row["step_limit"],
            history=history,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
