"""Configurable hybrid scoring with graceful signal degradation."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from projectmind.config import ScoringWeights
from projectmind.memory.store import tokenize
from projectmind.models.retrieval_models import ScoreBreakdown

SIGNAL_NAMES = (
    "graph_relevance",
    "semantic_similarity",
    "lexical_match",
    "recency_git",
    "architectural_importance",
    "test_coverage_bonus",
    "feedback_score",
)


def _weights_map(weights: ScoringWeights | Mapping[str, float] | None) -> dict[str, float]:
    if weights is None:
        return {key: float(value) for key, value in ScoringWeights().model_dump().items()}
    if isinstance(weights, ScoringWeights):
        return {key: float(value) for key, value in weights.model_dump().items()}
    result = {name: float(weights.get(name, 0.0)) for name in SIGNAL_NAMES}
    if any(not math.isfinite(value) or value < 0 for value in result.values()):
        raise ValueError("scoring weights must be finite and non-negative")
    if not any(result.values()):
        raise ValueError("at least one scoring weight must be positive")
    return result


def renormalized_score(
    signals: Mapping[str, float | None],
    weights: ScoringWeights | Mapping[str, float] | None = None,
) -> float:
    """Weight available signals only, preserving a [0, 1] result.

    A missing signal is represented by ``None`` or an absent key. A measured zero
    remains available and therefore still contributes its configured weight.
    """

    configured = _weights_map(weights)
    numerator = 0.0
    denominator = 0.0
    for name in SIGNAL_NAMES:
        value = signals.get(name)
        weight = configured[name]
        if value is None or weight == 0:
            continue
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
        numerator += weight * value
        denominator += weight
    if denominator == 0:
        return 0.0
    return min(1.0, max(0.0, numerator / denominator))


def hybrid_score(
    *,
    graph_relevance: float | None = None,
    semantic_similarity: float | None = None,
    lexical_match: float | None = None,
    recency_git: float | None = None,
    architectural_importance: float | None = None,
    test_coverage_bonus: float | None = None,
    feedback_score: float | None = None,
    weights: ScoringWeights | Mapping[str, float] | None = None,
) -> ScoreBreakdown:
    """Return both the normalized aggregate and its inspectable components."""

    signals = {
        "graph_relevance": graph_relevance,
        "semantic_similarity": semantic_similarity,
        "lexical_match": lexical_match,
        "recency_git": recency_git,
        "architectural_importance": architectural_importance,
        "test_coverage_bonus": test_coverage_bonus,
        "feedback_score": feedback_score,
    }
    final = renormalized_score(signals, weights)
    return ScoreBreakdown(
        graph_relevance=graph_relevance or 0.0,
        semantic_similarity=semantic_similarity,
        lexical_match=lexical_match or 0.0,
        recency_git=recency_git or 0.0,
        architectural_importance=architectural_importance or 0.0,
        test_coverage_bonus=test_coverage_bonus or 0.0,
        feedback_score=feedback_score or 0.0,
        final_score=final,
    )


def lexical_match(query: str, text: str) -> float:
    """A deterministic lexical score suited to identifiers and prose."""

    query_terms = list(dict.fromkeys(tokenize(query)))
    if not query_terms:
        return 0.0
    text_tokens = tokenize(text)
    text_terms = set(text_tokens)
    matched = sum(term in text_terms for term in query_terms)
    coverage = matched / len(query_terms)
    if coverage == 0:
        return 0.0
    normalized_query = " ".join(query_terms)
    normalized_text = " ".join(text_tokens)
    phrase_bonus = 0.15 if normalized_query in normalized_text else 0.0
    # A direct path/symbol mention deserves a small, bounded boost.
    raw_bonus = 0.1 if re.search(re.escape(query.strip()), text, flags=re.IGNORECASE) else 0.0
    return min(1.0, coverage * (1.0 - phrase_bonus) + phrase_bonus + raw_bonus)


# Backwards-friendly name for callers that think of the operation as a formula.
weighted_score = renormalized_score
