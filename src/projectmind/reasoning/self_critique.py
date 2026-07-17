"""Four-perspective critique over visible artefacts and supplied evidence."""

from __future__ import annotations

import re

from projectmind.database import Database
from projectmind.models.reasoning_models import Critique
from projectmind.reasoning.sequential_thinking import SequentialThinkingEngine

PERSPECTIVES = ("Architect", "Security", "Test Engineer", "Performance")

_DANGEROUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\beval\s*\("), "The artefact appears to introduce dynamic eval()."),
    (re.compile(r"\bexec\s*\("), "The artefact appears to introduce dynamic exec()."),
    (re.compile(r"shell\s*=\s*True"), "The artefact appears to enable a command shell."),
    (
        re.compile(r"(?:api[_-]?key|password|secret)\s*=", re.IGNORECASE),
        "A secret-like assignment needs review.",
    ),
)


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


def _critique(artefact: str, context: str, *, kind: str) -> list[Critique]:
    combined = f"{artefact}\n{context}"
    folded = combined.casefold()

    architecture_issues: list[str] = []
    if not any(
        marker in folded for marker in ("dependency", "interface", "module", "architecture")
    ):
        architecture_issues.append(
            "No architecture or dependency compatibility evidence is explicit."
        )
    if kind == "plan" and "pending" in folded:
        architecture_issues.append("The plan contains steps that have not been validated.")

    security_issues = [
        message for pattern, message in _DANGEROUS_PATTERNS if pattern.search(combined)
    ]
    if not security_issues and not any(
        marker in folded for marker in ("security", "threat", "secret scan", "owasp")
    ):
        security_issues.append("No security validation evidence is supplied.")

    test_issues: list[str] = []
    has_test_plan = any(marker in folded for marker in ("test", "pytest", "validation command"))
    has_test_result = any(
        marker in folded for marker in ("passed", "failed", " exit code ", "result:")
    )
    if not has_test_plan:
        test_issues.append("No targeted test or executable validation is identified.")
    elif not has_test_result:
        test_issues.append(
            "A validation activity is mentioned but no observable result is supplied."
        )

    performance_issues: list[str] = []
    makes_performance_claim = any(
        marker in folded
        for marker in ("faster", "performance improvement", "more efficient", "latency")
    )
    has_measurement = any(marker in folded for marker in ("benchmark", "ms", "ops/s", "profile"))
    if makes_performance_claim and not has_measurement:
        performance_issues.append("A performance claim is not backed by a measurement or baseline.")
    elif not has_measurement:
        performance_issues.append(
            "Performance impact is unmeasured; avoid making a performance claim."
        )

    return [
        Critique(
            perspective="Architect",
            issues=architecture_issues,
            severity="medium" if architecture_issues else "info",
            recommendation=(
                "Cite affected boundaries, dependencies, conventions, and rollback evidence."
            ),
        ),
        Critique(
            perspective="Security",
            issues=security_issues,
            severity="high"
            if any("appears to" in issue for issue in security_issues)
            else "medium",
            recommendation="Run the relevant secret and OWASP checks; document threat assumptions.",
        ),
        Critique(
            perspective="Test Engineer",
            issues=test_issues,
            severity="high" if not has_test_plan else "medium" if test_issues else "info",
            recommendation="Record the exact targeted and regression checks with their outcomes.",
        ),
        Critique(
            perspective="Performance",
            issues=performance_issues,
            severity="medium" if makes_performance_claim and not has_measurement else "info",
            recommendation="Measure against a baseline when performance is acceptance-relevant.",
        ),
    ]


def self_reflect(output: str, context: str = "") -> list[Critique]:
    """Critique a visible response; no private reasoning is requested or inferred."""

    return _critique(_required(output, "output"), context.strip(), kind="response")


def critique_code_change(diff: str, context: str = "") -> list[Critique]:
    """Critique a proposed diff without applying or executing it."""

    return _critique(_required(diff, "diff"), context.strip(), kind="code_change")


def critique_plan(
    plan_id: str,
    *,
    database: Database,
) -> list[Critique]:
    """Load and critique a durable visible plan by identifier."""

    plan = SequentialThinkingEngine(database).get_plan(_required(plan_id, "plan_id"))
    rendered = "\n".join(
        (
            f"Step {step.step_number} [{step.status.value}]: {step.description}\n"
            f"Criterion: {step.success_criteria}\nEvidence: {step.evidence or 'not supplied'}"
        )
        for step in plan.steps
    )
    return _critique(rendered, plan.task, kind="plan")


class SelfCritiqueEngine:
    """State-bound facade convenient for application composition."""

    def __init__(self, database: Database | None = None) -> None:
        self.database = database

    def self_reflect(self, output: str, context: str = "") -> list[Critique]:
        return self_reflect(output, context)

    def critique_code_change(self, diff: str, context: str = "") -> list[Critique]:
        return critique_code_change(diff, context)

    def critique_plan(self, plan_id: str) -> list[Critique]:
        if self.database is None:
            raise ValueError("database is required to critique a persisted plan")
        return critique_plan(plan_id, database=self.database)
