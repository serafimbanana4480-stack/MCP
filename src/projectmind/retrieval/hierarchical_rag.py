"""Progressive, hierarchy-aware fitting of ranked context into a token budget."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from projectmind.models.retrieval_models import ContextItem

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def estimate_tokens(text: str) -> int:
    """Conservative dependency-free approximation used consistently by retrieval."""

    if not text:
        return 0
    lexical = len(_TOKEN_RE.findall(text))
    byte_floor = math.ceil(len(text.encode("utf-8")) / 4)
    return max(1, lexical, byte_floor)


def truncate_to_tokens(text: str, budget: int) -> str:
    """Return a readable prefix that never exceeds the estimator's budget."""

    if budget <= 0:
        return ""
    if estimate_tokens(text) <= budget:
        return text
    low = 0
    high = len(text)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = text[:middle].rstrip() + " …"
        if estimate_tokens(candidate) <= budget:
            low = middle
        else:
            high = middle - 1
    if low == 0:
        return ""
    return text[:low].rstrip() + " …"


@dataclass(frozen=True, slots=True)
class RankedContext:
    """A context item plus its cheaper hierarchy levels."""

    item: ContextItem
    summary: str | None = None
    hierarchy: int = 1


def fit_context_to_budget(
    candidates: list[RankedContext],
    token_budget: int,
    *,
    minimum_item_tokens: int = 12,
) -> tuple[list[ContextItem], int]:
    """Choose ranked items, falling back from chunk to summary to bounded excerpt."""

    if token_budget < 0:
        raise ValueError("token_budget cannot be negative")
    if token_budget == 0:
        return [], 0
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.item.score.final_score,
            candidate.hierarchy,
            candidate.item.provenance.reference,
        ),
    )
    selected: list[ContextItem] = []
    remaining = token_budget
    seen: set[tuple[str, str]] = set()
    for candidate in ordered:
        item = candidate.item
        identity = (item.kind, item.provenance.reference)
        if identity in seen or remaining <= 0:
            continue
        content = item.content
        cost = estimate_tokens(content)
        if cost > remaining and candidate.summary:
            summary = candidate.summary.strip()
            summary_cost = estimate_tokens(summary)
            if summary and summary_cost <= cost:
                content, cost = summary, summary_cost
        if cost > remaining:
            if remaining < minimum_item_tokens:
                continue
            content = truncate_to_tokens(content, remaining)
            cost = estimate_tokens(content)
        if not content or cost <= 0 or cost > remaining:
            continue
        selected.append(item.model_copy(update={"content": content, "token_estimate": cost}))
        seen.add(identity)
        remaining -= cost
    return selected, token_budget - remaining
