"""Structured, evidence-honest implementation comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from projectmind.models.planning_models import ImplementationComparison


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


def _normalise_criteria(criteria: Sequence[str]) -> list[str]:
    cleaned = [criterion.strip() for criterion in criteria if criterion.strip()]
    unique = list(dict.fromkeys(cleaned))
    if not unique:
        raise ValueError("criteria must contain at least one non-empty item")
    if len(unique) > 20:
        raise ValueError("criteria cannot contain more than 20 items")
    return unique


def compare_implementations(
    option_a: str,
    option_b: str,
    criteria: Sequence[str],
    *,
    evidence_a: Mapping[str, str] | None = None,
    evidence_b: Mapping[str, str] | None = None,
    estimated_cost_a: str = "unknown - estimate required",
    estimated_cost_b: str = "unknown - estimate required",
    migration_effort_a: str = "unknown - dependency analysis required",
    migration_effort_b: str = "unknown - dependency analysis required",
) -> ImplementationComparison:
    """Compare two options without manufacturing a winner from their names."""

    clean_a = _required(option_a, "option_a")
    clean_b = _required(option_b, "option_b")
    if clean_a.casefold() == clean_b.casefold():
        raise ValueError("option_a and option_b must be distinct")
    clean_criteria = _normalise_criteria(criteria)
    provided_a = {key.strip(): value.strip() for key, value in (evidence_a or {}).items()}
    provided_b = {key.strip(): value.strip() for key, value in (evidence_b or {}).items()}

    advantages_a: list[str] = []
    advantages_b: list[str] = []
    disadvantages_a: list[str] = []
    disadvantages_b: list[str] = []
    missing: list[str] = []
    for criterion in clean_criteria:
        value_a = provided_a.get(criterion)
        value_b = provided_b.get(criterion)
        if value_a:
            advantages_a.append(f"{criterion}: supplied evidence - {value_a}")
        else:
            disadvantages_a.append(f"{criterion}: no evidence supplied")
            missing.append(f"{clean_a}/{criterion}")
        if value_b:
            advantages_b.append(f"{criterion}: supplied evidence - {value_b}")
        else:
            disadvantages_b.append(f"{criterion}: no evidence supplied")
            missing.append(f"{clean_b}/{criterion}")

    if missing:
        recommendation = (
            "No evidence-based winner. Collect comparable evidence for: " + ", ".join(missing) + "."
        )
    else:
        recommendation = (
            "Evidence is available for both options, but no preference direction or weighting was "
            "provided. Apply agreed weights or obtain a reviewer decision."
        )
    return ImplementationComparison(
        criteria=clean_criteria,
        option_a=clean_a,
        option_b=clean_b,
        advantages_a=advantages_a,
        advantages_b=advantages_b,
        disadvantages_a=disadvantages_a,
        disadvantages_b=disadvantages_b,
        estimated_cost_a=_required(estimated_cost_a, "estimated_cost_a"),
        estimated_cost_b=_required(estimated_cost_b, "estimated_cost_b"),
        migration_effort_a=_required(migration_effort_a, "migration_effort_a"),
        migration_effort_b=_required(migration_effort_b, "migration_effort_b"),
        recommendation=recommendation,
    )
