"""Durable long-task checkpoints, resumption, and post-mortem closure gate."""

from __future__ import annotations

import json
import sqlite3

from projectmind.database import Database
from projectmind.errors import ConflictError, NotFoundError
from projectmind.models.common import new_id, utc_now
from projectmind.models.planning_models import LongRunningTask
from projectmind.reasoning.post_mortem import LearningStore, record_learning
from projectmind.reasoning.sequential_thinking import SequentialThinkingEngine

_TERMINAL_STATUSES = {"completed", "abandoned"}


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


class LongRunningTaskService:
    """Manage crash-safe task state in SQLite."""

    def __init__(
        self,
        database: Database,
        *,
        sequential_engine: SequentialThinkingEngine | None = None,
        memory_store: LearningStore | None = None,
        require_post_mortem: bool = True,
    ) -> None:
        self.database = database
        self.sequential_engine = sequential_engine or SequentialThinkingEngine(database)
        self.memory_store = memory_store
        self.require_post_mortem = require_post_mortem

    def create_long_running_task(self, spec: str, *, max_steps: int = 8) -> LongRunningTask:
        clean_spec = _required(spec, "spec")
        plan = self.sequential_engine.sequential_think(clean_spec, max_steps=max_steps)
        task = LongRunningTask(
            id=new_id("ltask"),
            spec=clean_spec,
            plan_id=plan.plan_id,
            status="active",
        )
        timestamp = utc_now().isoformat()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO long_tasks(
                    id, spec, plan_id, status, checkpoints_json,
                    post_mortem_memory_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.spec,
                    task.plan_id,
                    task.status,
                    "[]",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
        return task

    def get_task(self, task_id: str) -> LongRunningTask:
        clean_task_id = _required(task_id, "task_id")
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM long_tasks WHERE id = ?", (clean_task_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"long task not found: {clean_task_id}")
        return self._from_row(row)

    def add_checkpoint(self, task_id: str, checkpoint: str) -> LongRunningTask:
        clean_task_id = _required(task_id, "task_id")
        clean_checkpoint = _required(checkpoint, "checkpoint")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM long_tasks WHERE id = ?", (clean_task_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"long task not found: {clean_task_id}")
            if str(row["status"]) in _TERMINAL_STATUSES:
                raise ConflictError("cannot add a checkpoint to a closed long task")
            checkpoints = self._checkpoints(row)
            if clean_checkpoint not in checkpoints:
                checkpoints.append(clean_checkpoint)
            connection.execute(
                "UPDATE long_tasks SET checkpoints_json = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(checkpoints, ensure_ascii=False),
                    utc_now().isoformat(),
                    clean_task_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM long_tasks WHERE id = ?", (clean_task_id,)
            ).fetchone()
        if updated is None:
            raise NotFoundError(f"long task not found after checkpoint: {clean_task_id}")
        return self._from_row(updated)

    checkpoint_task = add_checkpoint

    def pause_task(self, task_id: str) -> LongRunningTask:
        return self._set_nonterminal_status(task_id, "paused")

    def resume_task(self, task_id: str) -> LongRunningTask:
        """Restore durable state and mark a paused task active again."""

        task = self.get_task(task_id)
        if task.status in _TERMINAL_STATUSES:
            raise ConflictError(f"cannot resume a {task.status} long task")
        if task.status == "paused":
            return self._set_nonterminal_status(task.id, "active")
        return task

    def close_task(
        self,
        task_id: str,
        *,
        post_mortem_memory_id: str | None = None,
        outcome: str = "",
        what_went_well: str = "",
        what_failed: str = "",
        lessons: str = "",
    ) -> LongRunningTask:
        """Close only after a durable post-mortem when the gate is enabled."""

        task = self.get_task(task_id)
        if task.status in _TERMINAL_STATUSES:
            raise ConflictError(f"long task is already {task.status}")
        memory_id = post_mortem_memory_id.strip() if post_mortem_memory_id else None
        supplied_learning = any(
            value.strip() for value in (outcome, what_went_well, what_failed, lessons)
        )
        if memory_id is None and supplied_learning:
            result = record_learning(
                outcome,
                what_went_well,
                what_failed,
                lessons,
                memory_store=self.memory_store,
                tags=("post-mortem", "long-task", task.id),
                source="planning.long_running_tasks",
            )
            memory_id = result.memory_id

        if self.require_post_mortem and memory_id is None:
            raise ConflictError(
                "post-mortem gate: persist a learning record before closing this long task"
            )
        if memory_id is not None:
            with self.database.connect() as connection:
                memory = connection.execute(
                    "SELECT id FROM memories WHERE id = ? AND status != 'deleted'", (memory_id,)
                ).fetchone()
            if memory is None:
                raise NotFoundError(f"post-mortem memory not found: {memory_id}")

        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE long_tasks
                SET status = 'completed', post_mortem_memory_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (memory_id, utc_now().isoformat(), task.id),
            )
            connection.execute(
                "UPDATE plans SET status = 'completed', updated_at = ? WHERE id = ?",
                (utc_now().isoformat(), task.plan_id),
            )
            updated = connection.execute(
                "SELECT * FROM long_tasks WHERE id = ?", (task.id,)
            ).fetchone()
        if updated is None:
            raise NotFoundError(f"long task not found after close: {task.id}")
        return self._from_row(updated)

    def _set_nonterminal_status(self, task_id: str, status: str) -> LongRunningTask:
        clean_task_id = _required(task_id, "task_id")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT status FROM long_tasks WHERE id = ?", (clean_task_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"long task not found: {clean_task_id}")
            if str(row["status"]) in _TERMINAL_STATUSES:
                raise ConflictError("cannot change the status of a closed long task")
            connection.execute(
                "UPDATE long_tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now().isoformat(), clean_task_id),
            )
            updated = connection.execute(
                "SELECT * FROM long_tasks WHERE id = ?", (clean_task_id,)
            ).fetchone()
        if updated is None:
            raise NotFoundError(f"long task not found after status update: {clean_task_id}")
        return self._from_row(updated)

    @staticmethod
    def _checkpoints(row: sqlite3.Row) -> list[str]:
        try:
            value = json.loads(str(row["checkpoints_json"]))
        except (json.JSONDecodeError, TypeError) as error:
            raise ConflictError("long task checkpoints are corrupt") from error
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ConflictError("long task checkpoints are corrupt")
        return value

    @classmethod
    def _from_row(cls, row: sqlite3.Row) -> LongRunningTask:
        return LongRunningTask(
            id=str(row["id"]),
            spec=str(row["spec"]),
            plan_id=str(row["plan_id"]) if row["plan_id"] is not None else None,
            status=str(row["status"]),
            checkpoints=cls._checkpoints(row),
            post_mortem_memory_id=(
                str(row["post_mortem_memory_id"])
                if row["post_mortem_memory_id"] is not None
                else None
            ),
        )


LongRunningTaskManager = LongRunningTaskService


def create_long_running_task(
    database: Database,
    spec: str,
    *,
    max_steps: int = 8,
    memory_store: LearningStore | None = None,
    require_post_mortem: bool = True,
) -> LongRunningTask:
    """Functional adapter suitable for an MCP tool binding."""

    return LongRunningTaskService(
        database,
        memory_store=memory_store,
        require_post_mortem=require_post_mortem,
    ).create_long_running_task(spec, max_steps=max_steps)


def resume_task(database: Database, task_id: str) -> LongRunningTask:
    """Functional adapter for durable task resumption."""

    return LongRunningTaskService(database).resume_task(task_id)
