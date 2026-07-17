"""Hybrid retrieval query, score, and bounded context models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from projectmind.models.common import Provenance


class ScoreBreakdown(BaseModel):
    graph_relevance: float = Field(default=0, ge=0, le=1)
    semantic_similarity: float | None = Field(default=None, ge=0, le=1)
    lexical_match: float = Field(default=0, ge=0, le=1)
    recency_git: float = Field(default=0, ge=0, le=1)
    architectural_importance: float = Field(default=0, ge=0, le=1)
    test_coverage_bonus: float = Field(default=0, ge=0, le=1)
    feedback_score: float = Field(default=0, ge=0, le=1)
    final_score: float = Field(default=0, ge=0, le=1)


class ContextItem(BaseModel):
    kind: Literal["code", "memory", "graph"]
    content: str
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    token_estimate: int
    score: ScoreBreakdown
    provenance: Provenance


class ContextBundle(BaseModel):
    task: str
    mode: Literal["exploratory", "surgical", "debug"]
    items: list[ContextItem] = Field(default_factory=list)
    graph_summary: str
    tokens_used: int
    token_budget: int
    cache_hit: bool = False
    warnings: list[str] = Field(default_factory=list)

