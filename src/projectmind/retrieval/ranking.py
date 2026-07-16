from __future__ import annotations

import re


def lexical_score(query: str, text: str) -> float:
    terms = {x.lower() for x in re.findall(r"\w+", query) if len(x) > 2}
    if not terms:
        return 0.0
    words = set(re.findall(r"\w+", text.lower()))
    return min(1.0, len(terms & words) / len(terms))


def rank_file(
    query: str,
    row: dict,
    importance: float = 0.0,
    recency: float = 0.0,
    graph: float = 0.0,
    weights: dict[str, float] | None = None,
) -> dict:
    weights = weights or {
        "graph_relevance": 0.35,
        "semantic_similarity": 0.25,
        "lexical_match": 0.2,
        "recency_git": 0.1,
        "architectural_importance": 0.1,
    }
    lexical = lexical_score(query, f"{row.get('path', '')} {row.get('content', '')}")
    semantic = float(row.get("semantic", 0.0))
    breakdown = {
        "graph_relevance": graph,
        "semantic_similarity": semantic,
        "lexical_match": lexical,
        "recency_git": recency,
        "architectural_importance": importance,
    }
    return {
        **row,
        "relevance": sum(weights[k] * breakdown[k] for k in breakdown),
        "scoring_breakdown": breakdown,
    }
