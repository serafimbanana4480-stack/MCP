"""Persistent, branch-aware engineering memory."""

from projectmind.memory.branch_scoping import branch_is_visible, normalize_branch
from projectmind.memory.consolidation import (
    ConsolidationAdapter,
    DeterministicConsolidator,
    consolidate_memory,
)
from projectmind.memory.feedback import feedback_thumbs_down, feedback_thumbs_up
from projectmind.memory.store import MemoryStore

__all__ = [
    "ConsolidationAdapter",
    "DeterministicConsolidator",
    "MemoryStore",
    "branch_is_visible",
    "consolidate_memory",
    "feedback_thumbs_down",
    "feedback_thumbs_up",
    "normalize_branch",
]
