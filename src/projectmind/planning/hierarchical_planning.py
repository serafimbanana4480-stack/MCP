"""Deterministic epic -> story -> technical-task decomposition."""

from __future__ import annotations

import json

from projectmind.database import Database
from projectmind.models.common import new_id, stable_id, utc_now
from projectmind.models.planning_models import HierarchicalPlan, PlanTask
from projectmind.reasoning.similar_solutions import (
    SimilarSolutionAdapter,
    find_similar_past_solutions,
)

HIERARCHICAL_PROMPT = """Produce a visible execution hierarchy, not private reasoning.
1) State verified premises and unknowns. 2) Compare viable approaches. 3) Choose and justify
one approach. 4) Decompose it into epics, stories, and bounded technical tasks. Every leaf
must have an observable success criterion, checkpoint evidence, dependencies, and rollback."""


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


class HierarchicalPlanner:
    """Build a reviewable hierarchy and optionally persist its plan identity."""

    def __init__(
        self,
        database: Database | None = None,
        *,
        similar_solution_adapter: SimilarSolutionAdapter | None = None,
    ) -> None:
        self.database = database
        self.similar_solution_adapter = similar_solution_adapter

    def hierarchical_planning(self, goal: str) -> HierarchicalPlan:
        clean_goal = _required(goal, "goal")
        plan_id = new_id("hplan")
        prior_checkpoint: list[str] = []
        if self.similar_solution_adapter is not None:
            prior = find_similar_past_solutions(
                clean_goal, adapter=self.similar_solution_adapter, limit=3
            )
            if prior.solutions:
                references = ", ".join(solution.memory_id for solution in prior.solutions)
                prior_checkpoint.append(
                    f"Review candidate past solutions ({references}) and record compatibility "
                    "evidence."
                )

        def task(
            key: str,
            title: str,
            level: str,
            parent_id: str | None,
            *,
            checkpoints: list[str] | None = None,
            success: list[str] | None = None,
        ) -> PlanTask:
            return PlanTask(
                id=stable_id("ptask", plan_id, key),
                title=title,
                parent_id=parent_id,
                level=level,
                checkpoints=checkpoints or [],
                success_criteria=success or [],
            )

        epic = task(
            "epic",
            f"Deliver: {clean_goal[:160]}",
            "epic",
            None,
            success=["All child stories meet their evidence-backed success criteria."],
        )
        discovery = task(
            "story-discovery",
            "Establish constraints and acceptance",
            "story",
            epic.id,
            success=["Scope, constraints, dependencies, and acceptance checks are explicit."],
        )
        implementation = task(
            "story-implementation",
            "Implement through bounded, reversible proposals",
            "story",
            epic.id,
            success=["The selected approach is delivered in reviewable increments with rollback."],
        )
        validation = task(
            "story-validation",
            "Validate, critique, and close",
            "story",
            epic.id,
            success=["Validation evidence and reusable learning reconcile with the goal."],
        )

        tasks = [
            epic,
            discovery,
            task(
                "discover-context",
                "Retrieve current architecture, conventions, and related decisions",
                "technical_task",
                discovery.id,
                checkpoints=[
                    *prior_checkpoint,
                    "Record source references and explicitly note retrieval gaps.",
                ],
                success=["Every relied-on project fact has a current source reference."],
            ),
            task(
                "discover-acceptance",
                "Confirm acceptance criteria, exclusions, and unknowns",
                "technical_task",
                discovery.id,
                checkpoints=["Map each requested outcome to an observable check."],
                success=["Ambiguities are resolved or explicitly carried as risks."],
            ),
            implementation,
            task(
                "implement-select",
                "Compare alternatives and select the least risky adequate approach",
                "technical_task",
                implementation.id,
                checkpoints=["Record rejected alternatives, assumptions, and rollback conditions."],
                success=["The recommendation uses consistent criteria and identifies uncertainty."],
            ),
            task(
                "implement-propose",
                "Prepare the change in small reviewable increments",
                "technical_task",
                implementation.id,
                checkpoints=["Keep every mutation behind propose -> confirm -> apply."],
                success=["Each increment is independently reviewable, testable, and reversible."],
            ),
            validation,
            task(
                "validate-checks",
                "Run targeted validation and relevant regression checks",
                "technical_task",
                validation.id,
                checkpoints=["Record exact commands/checks, exit status, and failure output."],
                success=["All applicable acceptance checks have observable results."],
            ),
            task(
                "validate-close",
                "Critique four perspectives and record the post-mortem",
                "technical_task",
                validation.id,
                checkpoints=["Review architecture, security, tests, and performance."],
                success=["Outstanding risks are explicit and a durable lesson is recorded."],
            ),
        ]
        plan = HierarchicalPlan(
            plan_id=plan_id,
            goal=clean_goal,
            tasks=tasks,
            prompt_template=HIERARCHICAL_PROMPT,
        )
        if self.database is not None:
            timestamp = utc_now().isoformat()
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT INTO plans(id, task, status, capability_mode, created_at, updated_at)
                    VALUES (?, ?, 'active', 'deterministic', ?, ?)
                    """,
                    (plan_id, clean_goal, timestamp, timestamp),
                )
                connection.executemany(
                    """
                    INSERT INTO plan_tasks(
                        id, plan_id, parent_id, title, level, status,
                        checkpoints_json, success_json
                    )
                    VALUES (?, ?, ?, ?, ?, 'todo', ?, ?)
                    """,
                    [
                        (
                            item.id,
                            plan_id,
                            item.parent_id,
                            item.title,
                            item.level,
                            json.dumps(item.checkpoints, ensure_ascii=False),
                            json.dumps(item.success_criteria, ensure_ascii=False),
                        )
                        for item in tasks
                    ],
                )
        return plan


def hierarchical_planning(
    goal: str,
    *,
    database: Database | None = None,
    similar_solution_adapter: SimilarSolutionAdapter | None = None,
) -> HierarchicalPlan:
    """Functional adapter suitable for an MCP tool binding."""

    return HierarchicalPlanner(
        database, similar_solution_adapter=similar_solution_adapter
    ).hierarchical_planning(goal)
