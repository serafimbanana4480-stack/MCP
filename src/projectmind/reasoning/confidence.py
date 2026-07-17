"""Transparent confidence scoring based on observable evidence signals."""

from __future__ import annotations

import re

from projectmind.models.reasoning_models import ConfidenceScore

_PATH_REFERENCE = re.compile(r"(?:^|\s)(?:[\w.-]+[/\\])+[\w.-]+(?::\d+)?")
_TEST_EVIDENCE = re.compile(
    r"\b(?:pytest|unittest|ruff|mypy|npm test|cargo test|go test)\b.{0,80}"
    r"\b(?:pass(?:ed)?|ok|success)",
    re.IGNORECASE | re.DOTALL,
)
_ABSOLUTE_CLAIM = re.compile(
    r"\b(?:guaranteed|certainly|always correct|cannot fail)\b", re.IGNORECASE
)


def confidence_score(response: str, context: str = "") -> ConfidenceScore:
    """Score a response without using model introspection or fabricated certainty."""

    clean_response = response.strip()
    clean_context = context.strip()
    if not clean_response:
        return ConfidenceScore(
            score=0,
            justification="No response was supplied, so there is nothing to support.",
            uncertainties=["Response content is absent."],
        )

    combined = f"{clean_response}\n{clean_context}"
    folded = combined.casefold()
    score = 20
    support: list[str] = []
    uncertainties: list[str] = []

    if clean_context:
        score += 10
        support.append("Caller supplied comparison context.")
    else:
        uncertainties.append("No external context was supplied.")

    if _PATH_REFERENCE.search(combined):
        score += 15
        support.append("The material contains a concrete path/source reference.")
    else:
        uncertainties.append("No concrete source path or line reference was detected.")

    if _TEST_EVIDENCE.search(combined):
        score += 25
        support.append("An explicit successful validation command/result was reported.")
    else:
        uncertainties.append("No explicit successful automated validation result was detected.")

    if any(marker in folded for marker in ("trade-off", "tradeoff", "alternative", "rollback")):
        score += 10
        support.append("Alternatives, trade-offs, or rollback are discussed.")
    else:
        uncertainties.append("Alternatives and rollback are not explicit.")

    if any(marker in folded for marker in ("uncertain", "unknown", "assumption", "not verified")):
        score += 5
        support.append("Uncertainty or assumptions are explicitly calibrated.")
    else:
        uncertainties.append("Assumptions and unknowns are not explicitly calibrated.")

    if _ABSOLUTE_CLAIM.search(combined):
        score -= 15
        uncertainties.append("An absolute claim is present without a proof boundary.")

    bounded_score = min(100, max(0, score))
    return ConfidenceScore(
        score=bounded_score,
        justification=(
            f"Deterministic evidence rubric produced {bounded_score}/100; this is a support score, "
            "not a probability that the answer is true."
        ),
        supporting_evidence=support,
        uncertainties=uncertainties,
    )
