"""Deterministic probability x impact risk matrices."""

from __future__ import annotations

from projectmind.database import Database
from projectmind.errors import NotFoundError
from projectmind.models.planning_models import HierarchicalPlan, RiskItem


def _risk(description: str, probability: float, impact: float, mitigation: str) -> RiskItem:
    return RiskItem(
        description=description,
        probability=probability,
        impact=impact,
        score=probability * impact,
        mitigation=mitigation,
    )


def risk_assessment_matrix(
    plan: HierarchicalPlan | str,
    *,
    database: Database | None = None,
) -> list[RiskItem]:
    """Assess common delivery risks while labeling them as hypotheses to verify."""

    if isinstance(plan, HierarchicalPlan):
        goal = plan.goal
        task_count = len(plan.tasks)
    else:
        plan_id = plan.strip()
        if not plan_id:
            raise ValueError("plan_id cannot be empty")
        task_count = 0
        if database is None:
            goal = "the referenced plan"
        else:
            with database.connect() as connection:
                row = connection.execute(
                    "SELECT task FROM plans WHERE id = ?", (plan_id,)
                ).fetchone()
            if row is None:
                raise NotFoundError(f"plan not found: {plan_id}")
            goal = str(row["task"])

    complexity_adjustment = 0.05 if task_count >= 10 else 0.0
    risks = [
        _risk(
            f"Acceptance ambiguity could cause incomplete delivery of {goal[:100]!r}.",
            0.45,
            0.70,
            "Map every requested outcome to an observable check and track unresolved questions.",
        ),
        _risk(
            "An integration or compatibility regression may affect existing callers.",
            min(1.0, 0.40 + complexity_adjustment),
            0.80,
            "Identify dependants, stage changes, run regression checks, and retain rollback.",
        ),
        _risk(
            "Validation gaps may allow a change to appear complete without evidence.",
            0.35,
            0.90,
            "Require exact commands/checks and results for each acceptance criterion.",
        ),
        _risk(
            "Migration or state changes may be difficult to reverse.",
            0.25,
            0.80,
            "Separate irreversible steps, test rollback, and define a cutover gate.",
        ),
        _risk(
            "External dependencies or unknown ownership may delay delivery.",
            0.30,
            0.60,
            "Assign owners and deadlines to dependencies; provide a bounded fallback.",
        ),
    ]
    risks.sort(key=lambda item: (-item.score, item.description))
    return risks
