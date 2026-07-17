"""Adapter boundary for analogical retrieval of past engineering solutions."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from projectmind.memory.store import MemoryStore
from projectmind.models.memory_models import MemoryType


class SimilarSolution(BaseModel):
    memory_id: str
    summary: str
    score: float = Field(ge=0, le=1)
    memory_type: MemoryType
    matched_terms: list[str] = Field(default_factory=list)


class SimilarSolutionsResult(BaseModel):
    task_description: str
    solutions: list[SimilarSolution] = Field(default_factory=list)
    capability_mode: Literal["deterministic", "llm_enhanced"] = "deterministic"
    search_note: str


class SimilarSolutionAdapter(Protocol):
    """Provider-neutral boundary; embedding adapters can implement this protocol."""

    capability_mode: Literal["deterministic", "llm_enhanced"]
    search_note: str

    def find_similar(self, task_description: str, limit: int) -> list[SimilarSolution]: ...


class MemoryStoreSolutionAdapter:
    """Honest lexical fallback over the local MemoryStore.

    It does not label lexical overlap as semantic similarity. A vector-backed
    implementation can be injected through ``SimilarSolutionAdapter`` later.
    """

    capability_mode: Literal["deterministic"] = "deterministic"
    search_note = (
        "Local lexical memory search was used; scores are not embedding similarity claims."
    )

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def find_similar(self, task_description: str, limit: int) -> list[SimilarSolution]:
        candidates = self.store.search(task_description, limit=max(limit * 4, limit))
        allowed_types = {MemoryType.PLAN, MemoryType.LESSON, MemoryType.BUG}
        return [
            SimilarSolution(
                memory_id=result.entry.id,
                summary=result.entry.summary or result.entry.content,
                score=result.score,
                memory_type=result.entry.type,
                matched_terms=result.matched_terms,
            )
            for result in candidates
            if result.entry.type in allowed_types
        ][:limit]


def find_similar_past_solutions(
    task_description: str,
    *,
    adapter: SimilarSolutionAdapter | None = None,
    memory_store: MemoryStore | None = None,
    limit: int = 5,
) -> SimilarSolutionsResult:
    """Retrieve analogous records without hiding which capability performed the search."""

    clean_task = task_description.strip()
    if not clean_task:
        raise ValueError("task_description cannot be empty")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if adapter is not None and memory_store is not None:
        raise ValueError("provide adapter or memory_store, not both")
    selected = adapter or (MemoryStoreSolutionAdapter(memory_store) if memory_store else None)
    if selected is None:
        return SimilarSolutionsResult(
            task_description=clean_task,
            solutions=[],
            search_note=(
                "No similarity adapter was configured; no past-solution similarity claim was made."
            ),
        )
    return SimilarSolutionsResult(
        task_description=clean_task,
        solutions=selected.find_similar(clean_task, limit),
        capability_mode=selected.capability_mode,
        search_note=selected.search_note,
    )
