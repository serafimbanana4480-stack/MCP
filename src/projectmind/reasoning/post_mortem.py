"""Post-mortem recording with an optional persistent memory boundary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel

from projectmind.models.memory_models import MemoryEntry


class LearningStore(Protocol):
    """Minimal MemoryStore-compatible boundary used by reasoning and planning."""

    def record_learning(
        self,
        outcome: str,
        *,
        what_went_well: str = "",
        what_failed: str = "",
        lessons: str = "",
        tags: Iterable[str] = (),
        related_node_ids: Iterable[str] = (),
        branch: str | None = None,
        confidence: float | None = None,
        source: str = "user",
    ) -> MemoryEntry: ...


class PostMortemResult(BaseModel):
    outcome: str
    what_went_well: str
    what_failed: str
    lessons: str
    persisted: bool
    memory_id: str | None = None
    warning: str | None = None


def record_learning(
    outcome: str,
    what_went_well: str = "",
    what_failed: str = "",
    lessons: str = "",
    *,
    memory_store: LearningStore | None = None,
    tags: Iterable[str] = ("post-mortem",),
    related_node_ids: Iterable[str] = (),
    branch: str | None = None,
    confidence: float | None = None,
    source: str = "reasoning.post_mortem",
) -> PostMortemResult:
    """Record a lesson through MemoryStore when one is composed into the app."""

    clean_outcome = outcome.strip()
    clean_well = what_went_well.strip()
    clean_failed = what_failed.strip()
    clean_lessons = lessons.strip()
    if not clean_outcome:
        raise ValueError("outcome cannot be empty")
    if not clean_lessons:
        raise ValueError("lessons cannot be empty")

    if memory_store is None:
        return PostMortemResult(
            outcome=clean_outcome,
            what_went_well=clean_well,
            what_failed=clean_failed,
            lessons=clean_lessons,
            persisted=False,
            warning="MemoryStore is unavailable; the post-mortem was returned but not persisted.",
        )

    entry = memory_store.record_learning(
        clean_outcome,
        what_went_well=clean_well,
        what_failed=clean_failed,
        lessons=clean_lessons,
        tags=tags,
        related_node_ids=related_node_ids,
        branch=branch,
        confidence=confidence,
        source=source,
    )
    return PostMortemResult(
        outcome=clean_outcome,
        what_went_well=clean_well,
        what_failed=clean_failed,
        lessons=clean_lessons,
        persisted=True,
        memory_id=entry.id,
    )
