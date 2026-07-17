"""A bounded, durable ReAct process coordinator.

Only observable action records and counters are persisted. The caller-provided
``current_thought`` is used as a turn signal but is never written to SQLite.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

from projectmind.database import Database
from projectmind.errors import ConflictError
from projectmind.models.common import utc_now
from projectmind.models.reasoning_models import ReactResult

ActionRecord = str | Mapping[str, object]

_COMPLETION_MARKERS = ("completed", "complete", "done", "success", "passed")
_FAILURE_MARKERS = ("failed", "failure", "error", "blocked", "timeout")
_OBSERVABLE_ACTION_FIELDS = {
    "action",
    "arguments",
    "error",
    "name",
    "observation",
    "result",
    "status",
    "tool",
}


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


def _normalise_actions(actions: Sequence[ActionRecord]) -> list[str]:
    normalised: list[str] = []
    for action in actions:
        if isinstance(action, str):
            value = action.strip()
        else:
            visible = {
                str(key): item
                for key, item in action.items()
                if str(key).casefold() in _OBSERVABLE_ACTION_FIELDS
            }
            value = json.dumps(visible, ensure_ascii=False, sort_keys=True, default=str).strip()
            if not visible:
                value = ""
        if value:
            normalised.append(value)
    # A bounded state also prevents action-history growth from becoming its own loop.
    return normalised[-25:]


class ReActLoop:
    """Persist iteration state and recommend one observable next action."""

    def __init__(self, database: Database, *, max_iterations: int = 15) -> None:
        if not 1 <= max_iterations <= 100:
            raise ValueError("max_iterations must be between 1 and 100")
        self.database = database
        self.max_iterations = max_iterations

    def react_step(
        self,
        task_id: str,
        current_thought: str,
        previous_actions: Sequence[ActionRecord] = (),
    ) -> ReactResult:
        clean_task_id = _required(task_id, "task_id")
        _required(current_thought, "current_thought")
        actions = _normalise_actions(previous_actions)

        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT iteration, state_json FROM react_states WHERE task_id = ?",
                (clean_task_id,),
            ).fetchone()
            previous_iteration = int(row["iteration"]) if row is not None else 0
            if row is not None:
                try:
                    previous_state = json.loads(str(row["state_json"]))
                except (json.JSONDecodeError, TypeError) as error:
                    raise ConflictError("persisted ReAct state is corrupt") from error
                if not isinstance(previous_state, dict):
                    raise ConflictError("persisted ReAct state is corrupt")
                if previous_state.get("should_stop") is True:
                    return ReactResult(
                        task_id=clean_task_id,
                        iteration=previous_iteration,
                        next_thought=(
                            "The loop is already stopped; reset it before another iteration."
                        ),
                        suggested_action="reset_react_loop",
                        suggested_arguments={"task_id": clean_task_id},
                        should_stop=True,
                        warning="The persisted ReAct loop is terminal.",
                    )
            iteration = min(previous_iteration + 1, self.max_iterations)

            result = self._next_result(clean_task_id, iteration, actions)
            state = {
                "actions": actions,
                "should_stop": result.should_stop,
                "warning": result.warning,
                "persisted_fields": "observable_actions_only",
            }
            connection.execute(
                """
                INSERT INTO react_states(task_id, iteration, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    iteration = excluded.iteration,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    clean_task_id,
                    iteration,
                    json.dumps(state, ensure_ascii=False, sort_keys=True),
                    utc_now().isoformat(),
                ),
            )
        return result

    def reset(self, task_id: str) -> bool:
        clean_task_id = _required(task_id, "task_id")
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "DELETE FROM react_states WHERE task_id = ?", (clean_task_id,)
            )
        return cursor.rowcount > 0

    def _next_result(
        self,
        task_id: str,
        iteration: int,
        actions: Sequence[str],
    ) -> ReactResult:
        action_history = " ".join(actions).casefold()
        completed = bool(actions) and _contains_marker(action_history, _COMPLETION_MARKERS)
        failed = bool(actions) and _contains_marker(action_history, _FAILURE_MARKERS)

        if completed:
            return ReactResult(
                task_id=task_id,
                iteration=iteration,
                next_thought=(
                    "The observable action history reports completion; verify closure evidence."
                ),
                suggested_action="record_learning",
                suggested_arguments={"task_id": task_id},
                should_stop=True,
            )
        if iteration >= self.max_iterations:
            return ReactResult(
                task_id=task_id,
                iteration=iteration,
                next_thought=(
                    "The iteration budget is exhausted; stop and reassess from observable evidence."
                ),
                suggested_action="explore_alternatives",
                suggested_arguments={"task_id": task_id, "num_branches": 3},
                should_stop=True,
                warning=(
                    f"ReAct limit of {self.max_iterations} iterations reached; "
                    "no further loop step was authorised."
                ),
            )
        if not actions:
            action = "get_relevant_context"
            arguments: dict[str, object] = {"task": task_id, "mode": "surgical"}
            guidance = "Collect project evidence before selecting an implementation action."
        elif failed:
            action = "self_reflect"
            arguments = {"task_id": task_id, "basis": "observable_failure"}
            guidance = "Inspect the recorded failure and challenge the current approach."
        else:
            action = "validate_step"
            arguments = {"task_id": task_id, "basis": "latest_observable_action"}
            guidance = "Validate the latest bounded action against its explicit success criterion."
        return ReactResult(
            task_id=task_id,
            iteration=iteration,
            next_thought=guidance,
            suggested_action=action,
            suggested_arguments=arguments,
        )


def _contains_marker(text: str, markers: Sequence[str]) -> bool:
    return any(re.search(rf"\b{re.escape(marker)}\b", text) is not None for marker in markers)


def react_step(
    database: Database,
    task_id: str,
    current_thought: str,
    previous_actions: Sequence[ActionRecord] = (),
    *,
    max_iterations: int = 15,
) -> ReactResult:
    """Functional adapter suitable for an MCP tool binding."""

    return ReActLoop(database, max_iterations=max_iterations).react_step(
        task_id, current_thought, previous_actions
    )
