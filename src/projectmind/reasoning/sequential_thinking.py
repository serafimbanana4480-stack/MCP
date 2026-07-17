"""Persistent, auditable execution checklists.

Despite the historical ``ThoughtStep`` model name, this module never asks for or
stores private chain-of-thought.  Persisted steps are short actions, observable
success criteria, and user/tool supplied evidence only.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Literal

from projectmind.database import Database
from projectmind.errors import ConflictError, NotFoundError
from projectmind.models.common import new_id, utc_now
from projectmind.models.reasoning_models import SequentialPlan, StepStatus, ThoughtStep

CAPABILITY_MODES = {"deterministic", "llm_enhanced"}

VISIBLE_PLAN_PROMPT = """Create an auditable execution checklist, not private reasoning.
For every step provide: (1) one bounded action, (2) an observable success criterion,
and (3) the evidence that a reviewer or tool can verify. State assumptions and
uncertainties explicitly. Do not invent repository facts or test results."""

_STEP_TEMPLATES: tuple[tuple[str, str], ...] = (
    (
        "Establish the task scope and collect relevant project context.",
        "The scope, constraints, affected components, and source references are listed.",
    ),
    (
        "Review applicable decisions, conventions, and similar past work.",
        "Relevant records are cited, or the evidence explicitly records that none were found.",
    ),
    (
        "Translate the request into explicit acceptance criteria.",
        "Each requested outcome has an observable check and unresolved ambiguity is recorded.",
    ),
    (
        "Select a bounded implementation approach and identify its risks.",
        "The chosen approach, rejected alternatives, assumptions, and mitigations are reviewable.",
    ),
    (
        "Prepare the implementation as a small, reversible change proposal.",
        "The proposed change has a reviewable scope and does not bypass the mutation boundary.",
    ),
    (
        "Run the narrowest relevant automated validation.",
        "The exact validation command or check and its observable result are recorded.",
    ),
    (
        "Check architecture, security, tests, and performance implications.",
        "All four perspectives have findings or an explicit evidence-backed no-finding result.",
    ),
    (
        "Close the task with outcome evidence and reusable learning.",
        "Acceptance criteria are reconciled with evidence and the post-mortem is recorded.",
    ),
)


def _clean_required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


def _select_templates(max_steps: int) -> Sequence[tuple[str, str]]:
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    if max_steps == 1:
        return (
            (
                "Complete the bounded task through scope, proposal, validation, and closure.",
                "The requested outcome, relevant evidence, validation result, and learning are "
                "recorded.",
            ),
        )
    if max_steps >= len(_STEP_TEMPLATES):
        return _STEP_TEMPLATES

    # A maximum is a budget, not a request to omit closure. Keep the first and
    # final lifecycle stages and sample the middle deterministically.
    interior = _STEP_TEMPLATES[1:-1]
    slots = max_steps - 2
    if slots <= 0:
        return (_STEP_TEMPLATES[0], _STEP_TEMPLATES[-1])
    indices = [round(index * (len(interior) - 1) / max(slots - 1, 1)) for index in range(slots)]
    chosen = tuple(interior[index] for index in dict.fromkeys(indices))
    return (_STEP_TEMPLATES[0], *chosen, _STEP_TEMPLATES[-1])[:max_steps]


class SequentialThinkingEngine:
    """Create and validate durable visible plans."""

    def __init__(
        self,
        database: Database,
        *,
        capability_mode: Literal["deterministic", "llm_enhanced"] = "deterministic",
    ) -> None:
        if capability_mode not in CAPABILITY_MODES:
            raise ValueError(f"unsupported capability_mode: {capability_mode}")
        self.database = database
        self.capability_mode = capability_mode

    def sequential_think(self, task: str, max_steps: int = 8) -> SequentialPlan:
        """Persist a bounded execution checklist for ``task``.

        The deterministic engine supplies process scaffolding only. It deliberately
        does not claim to have inferred repository-specific implementation details.
        """

        clean_task = _clean_required(task, "task")
        templates = _select_templates(max_steps)
        plan_id = new_id("plan")
        steps = [
            ThoughtStep(
                id=new_id("step"),
                plan_id=plan_id,
                step_number=number,
                description=description,
                success_criteria=criterion,
            )
            for number, (description, criterion) in enumerate(templates, start=1)
        ]
        timestamp = utc_now().isoformat()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO plans(id, task, status, capability_mode, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?, ?)
                """,
                (plan_id, clean_task, self.capability_mode, timestamp, timestamp),
            )
            connection.executemany(
                """
                INSERT INTO thought_steps(
                    id, plan_id, step_number, description, success_criteria, status, evidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        step.id,
                        step.plan_id,
                        step.step_number,
                        step.description,
                        step.success_criteria,
                        step.status.value,
                        step.evidence,
                    )
                    for step in steps
                ],
            )
        return SequentialPlan(
            plan_id=plan_id,
            task=clean_task,
            steps=steps,
            prompt_template=VISIBLE_PLAN_PROMPT,
            capability_mode=self.capability_mode,
        )

    def get_plan(self, plan_id: str) -> SequentialPlan:
        clean_plan_id = _clean_required(plan_id, "plan_id")
        with self.database.connect() as connection:
            plan_row = connection.execute(
                "SELECT id, task, capability_mode FROM plans WHERE id = ?",
                (clean_plan_id,),
            ).fetchone()
            if plan_row is None:
                raise NotFoundError(f"plan not found: {clean_plan_id}")
            step_rows = connection.execute(
                """
                SELECT id, plan_id, step_number, description, success_criteria, status, evidence
                FROM thought_steps WHERE plan_id = ? ORDER BY step_number, id
                """,
                (clean_plan_id,),
            ).fetchall()
        return SequentialPlan(
            plan_id=str(plan_row["id"]),
            task=str(plan_row["task"]),
            steps=[self._step_from_row(row) for row in step_rows],
            prompt_template=VISIBLE_PLAN_PROMPT,
            capability_mode=str(plan_row["capability_mode"]),
        )

    def validate_step(
        self,
        step_id: str,
        evidence: str,
        *,
        succeeded: bool = True,
    ) -> ThoughtStep:
        """Record externally supplied evidence and its explicit pass/fail outcome.

        This method never guesses whether prose proves a criterion. ``succeeded`` is
        an assertion made by the caller after observing a tool or reviewer result.
        Later steps cannot be validated while an earlier step remains unresolved.
        """

        clean_step_id = _clean_required(step_id, "step_id")
        clean_evidence = _clean_required(evidence, "evidence")
        target_status = StepStatus.VALIDATED if succeeded else StepStatus.FAILED
        timestamp = utc_now().isoformat()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT id, plan_id, step_number, description, success_criteria, status, evidence
                FROM thought_steps WHERE id = ?
                """,
                (clean_step_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"step not found: {clean_step_id}")

            if succeeded:
                unresolved = connection.execute(
                    """
                    SELECT id, step_number, status FROM thought_steps
                    WHERE plan_id = ? AND step_number < ? AND status != 'validated'
                    ORDER BY step_number LIMIT 1
                    """,
                    (row["plan_id"], row["step_number"]),
                ).fetchone()
                if unresolved is not None:
                    raise ConflictError(
                        "cannot validate a later step before earlier step "
                        f"{unresolved['step_number']} is validated"
                    )

            connection.execute(
                "UPDATE thought_steps SET status = ?, evidence = ? WHERE id = ?",
                (target_status.value, clean_evidence, clean_step_id),
            )
            if succeeded:
                remaining = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM thought_steps
                        WHERE plan_id = ? AND status != 'validated'
                        """,
                        (row["plan_id"],),
                    ).fetchone()[0]
                )
                plan_status = "validated" if remaining == 0 else "active"
            else:
                plan_status = "needs_revision"
            connection.execute(
                "UPDATE plans SET status = ?, updated_at = ? WHERE id = ?",
                (plan_status, timestamp, row["plan_id"]),
            )
            updated = connection.execute(
                """
                SELECT id, plan_id, step_number, description, success_criteria, status, evidence
                FROM thought_steps WHERE id = ?
                """,
                (clean_step_id,),
            ).fetchone()
        if updated is None:  # Defensive: the row is protected by the transaction.
            raise NotFoundError(f"step not found after update: {clean_step_id}")
        return self._step_from_row(updated)

    @staticmethod
    def _step_from_row(row: sqlite3.Row) -> ThoughtStep:
        return ThoughtStep(
            id=str(row["id"]),
            plan_id=str(row["plan_id"]),
            step_number=int(row["step_number"]),
            description=str(row["description"]),
            success_criteria=str(row["success_criteria"]),
            status=StepStatus(str(row["status"])),
            evidence=(str(row["evidence"]) if row["evidence"] is not None else None),
        )


def sequential_think(
    database: Database,
    task: str,
    max_steps: int = 8,
    *,
    capability_mode: Literal["deterministic", "llm_enhanced"] = "deterministic",
) -> SequentialPlan:
    """Functional adapter suitable for an MCP tool binding."""

    return SequentialThinkingEngine(database, capability_mode=capability_mode).sequential_think(
        task, max_steps
    )


def validate_step(
    database: Database,
    step_id: str,
    evidence: str,
    *,
    succeeded: bool = True,
) -> ThoughtStep:
    """Functional adapter for durable step validation."""

    return SequentialThinkingEngine(database).validate_step(step_id, evidence, succeeded=succeeded)
