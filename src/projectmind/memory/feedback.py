"""Small feedback operations used by memory and retrieval ranking."""

from __future__ import annotations

from projectmind.models.memory_models import MemoryEntry


def feedback_thumbs_up(store: MemoryStore, memory_id: str) -> MemoryEntry:
    """Record positive feedback while keeping the persisted score bounded."""

    return store.apply_feedback(memory_id, positive=True)


def feedback_thumbs_down(store: MemoryStore, memory_id: str) -> MemoryEntry:
    """Record negative feedback while keeping the persisted score bounded."""

    return store.apply_feedback(memory_id, positive=False)


# Delayed import avoids a runtime cycle while retaining a useful annotation.
from projectmind.memory.store import MemoryStore  # noqa: E402
