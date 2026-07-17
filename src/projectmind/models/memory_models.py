"""Long-term engineering memory models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from projectmind.models.common import utc_now


class MemoryType(str, Enum):
    DECISION = "decision"
    BUG = "bug"
    CONVENTION = "convention"
    PLAN = "plan"
    LESSON = "lesson"


class MemoryEntry(BaseModel):
    id: str
    type: MemoryType
    content: str
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0, le=1)
    initial_confidence: float = Field(default=0.7, ge=0, le=1)
    last_verified: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    branch: str | None = None
    source: str = "user"
    feedback_score: float = 0.0
    superseded_by: str | None = None
    status: str = "active"


class MemorySearchResult(BaseModel):
    entry: MemoryEntry
    lexical_score: float = Field(ge=0, le=1)
    effective_confidence: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=1)
    matched_terms: list[str] = Field(default_factory=list)


class ConsolidationResult(BaseModel):
    consolidated: list[MemoryEntry] = Field(default_factory=list)
    superseded_ids: list[str] = Field(default_factory=list)
    skipped_clusters: int = 0
    capability_mode: str = "deterministic"

