"""Deterministic alternative exploration with explicit capability boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol

from projectmind.models.reasoning_models import (
    Alternative,
    AlternativesResult,
    ConfidenceScore,
)

ALTERNATIVES_PROMPT = """Evaluate the task without exposing private chain-of-thought.
1) List verified premises and unknowns. 2) Describe 3-5 materially distinct approaches.
3) For each, list benefits, costs, failure modes, rollback, and evidence needed.
4) Rank using the same criteria and explain the recommendation. Never invent project facts."""


class AlternativeGenerator(Protocol):
    """Boundary for an optional model/provider-backed branch generator."""

    capability_mode: Literal["deterministic", "llm_enhanced"]

    def generate(self, task: str, num_branches: int) -> Sequence[Alternative]: ...


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} cannot be empty")
    return cleaned


def _confidence(score: int, basis: str, uncertainty: str) -> ConfidenceScore:
    return ConfidenceScore(
        score=score,
        justification=basis,
        supporting_evidence=["Deterministic process heuristic; repository evidence not supplied."],
        uncertainties=[uncertainty],
    )


def _deterministic_catalog(task: str) -> list[Alternative]:
    scope = task[:120]
    return [
        Alternative(
            title="Incremental change",
            approach=f"Make the smallest reversible change that can satisfy: {scope}",
            pros=[
                "Limits blast radius and review size.",
                "Supports targeted validation and straightforward rollback.",
            ],
            cons=[
                "May preserve an existing structural limitation.",
                "Can accumulate follow-up work if the boundary is already unsuitable.",
            ],
            risks=challenge_plan("incremental change"),
            confidence=_confidence(
                76,
                "Ranked highly because reversibility and bounded scope are generally safer "
                "defaults.",
                "Fitness depends on repository architecture and acceptance criteria not provided "
                "here.",
            ),
        ),
        Alternative(
            title="Boundary-first extension",
            approach=(
                "Introduce or strengthen an adapter/interface boundary, then implement the "
                "requested "
                f"behaviour behind it: {scope}"
            ),
            pros=[
                "Separates provider-specific behaviour from domain logic.",
                "Creates a test seam and a future replacement point.",
            ],
            cons=[
                "Adds abstraction and more types to maintain.",
                "May be unnecessary for a single stable implementation.",
            ],
            risks=challenge_plan("boundary-first extension"),
            confidence=_confidence(
                72,
                "A boundary improves replaceability, but its value must be justified by real "
                "variation.",
                "No evidence yet shows that multiple implementations or providers are required.",
            ),
        ),
        Alternative(
            title="Evidence-first spike",
            approach=(
                "Run a time-boxed, non-production experiment to resolve the largest unknown before "
                f"choosing an implementation for: {scope}"
            ),
            pros=[
                "Reduces uncertainty before committing to a design.",
                "Can produce measurements and a concrete rollback decision.",
            ],
            cons=[
                "Delays production delivery.",
                "The spike must be discarded or deliberately hardened.",
            ],
            risks=challenge_plan("evidence-first spike"),
            confidence=_confidence(
                68,
                "Useful when key facts are unknown; deliberately not ranked first without proof "
                "of uncertainty.",
                "The highest-risk unknown has not been identified from repository evidence.",
            ),
        ),
        Alternative(
            title="Staged parallel migration",
            approach=(
                "Add the new path beside the old one, validate equivalence, migrate callers in "
                "stages, "
                f"then remove the old path for: {scope}"
            ),
            pros=[
                "Allows incremental rollout and rollback.",
                "Makes behavioural comparison possible during migration.",
            ],
            cons=[
                "Temporarily maintains two implementations.",
                "Requires an explicit cutover and removal plan.",
            ],
            risks=challenge_plan("staged parallel migration"),
            confidence=_confidence(
                61,
                "Staging controls migration risk but carries meaningful temporary complexity.",
                "It is unknown whether compatibility or zero-downtime migration is needed.",
            ),
        ),
        Alternative(
            title="Focused replacement",
            approach=f"Replace the affected implementation in one coordinated change for: {scope}",
            pros=[
                "Avoids a prolonged dual-system state.",
                "Can simplify an obsolete implementation when full coverage exists.",
            ],
            cons=[
                "Has the largest immediate blast radius.",
                "Requires strong regression coverage and a tested rollback plan.",
            ],
            risks=challenge_plan("focused replacement"),
            confidence=_confidence(
                45,
                "A replacement may be valid, but the deterministic baseline lacks evidence to "
                "justify its risk.",
                "Current test coverage, coupling, migration constraints, and rollback viability "
                "are unknown.",
            ),
        ),
    ]


def challenge_plan(approach: str) -> list[str]:
    """Return explicit challenges without pretending they are observed defects."""

    clean_approach = _required(approach, "approach")
    return [
        f"Verify that {clean_approach!r} satisfies every acceptance criterion.",
        "Identify the failure signal and a reversible rollback before implementation.",
        "Check compatibility with recorded architecture and conventions using project evidence.",
    ]


def explore_alternatives(
    task: str,
    num_branches: int = 3,
    *,
    generator: AlternativeGenerator | None = None,
) -> AlternativesResult:
    """Return 3-5 challenged alternatives, ranked by an explicit score."""

    clean_task = _required(task, "task")
    if not 3 <= num_branches <= 5:
        raise ValueError("num_branches must be between 3 and 5")

    capability_mode: Literal["deterministic", "llm_enhanced"] = "deterministic"
    if generator is None:
        alternatives = _deterministic_catalog(clean_task)[:num_branches]
    else:
        alternatives = list(generator.generate(clean_task, num_branches))
        if len(alternatives) != num_branches:
            raise ValueError("alternative generator returned an unexpected branch count")
        capability_mode = generator.capability_mode
        alternatives = [
            alternative.model_copy(
                update={
                    "risks": list(
                        dict.fromkeys([*alternative.risks, *challenge_plan(alternative.title)])
                    )
                }
            )
            for alternative in alternatives
        ]

    alternatives.sort(key=lambda item: (-item.confidence.score, item.title.casefold()))
    winner = alternatives[0]
    return AlternativesResult(
        task=clean_task,
        alternatives=alternatives,
        recommended_index=0,
        recommendation=(
            f"{winner.title} ranks first at {winner.confidence.score}/100 under the available "
            "evidence. Re-evaluate the ranking after repository evidence, constraints, and "
            "validation data are supplied."
        ),
        prompt_template=ALTERNATIVES_PROMPT,
        capability_mode=capability_mode,
    )
