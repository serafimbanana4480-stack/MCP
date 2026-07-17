"""Deterministic memory consolidation with an optional, injected LLM boundary."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from projectmind.database import Database
from projectmind.memory.store import MemoryStore, tokenize
from projectmind.models.common import stable_id, utc_now
from projectmind.models.memory_models import ConsolidationResult, MemoryEntry, MemoryType


@runtime_checkable
class ConsolidationAdapter(Protocol):
    """Optional summarization boundary.

    The core never performs network I/O. Applications may inject a local or remote
    adapter after obtaining whatever consent their policy requires.
    """

    def consolidate(self, entries: Sequence[MemoryEntry]) -> str:
        """Return the consolidated factual content for a stable list of entries."""


class DeterministicConsolidator:
    """Cluster related active memories and preserve a complete audit trail."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        adapter: ConsolidationAdapter | None = None,
        min_cluster_size: int | None = None,
        lexical_threshold: float = 0.45,
    ) -> None:
        self.store = store
        self.adapter = adapter
        self.min_cluster_size = (
            store.config.consolidation_min_cluster_size
            if min_cluster_size is None
            else min_cluster_size
        )
        if self.min_cluster_size < 2:
            raise ValueError("min_cluster_size must be at least 2")
        if not 0 <= lexical_threshold <= 1:
            raise ValueError("lexical_threshold must be between 0 and 1")
        self.lexical_threshold = lexical_threshold

    def consolidate(
        self,
        entries: Sequence[MemoryEntry] | None = None,
        *,
        memory_type: MemoryType | str | None = None,
        branch: str | None = None,
    ) -> ConsolidationResult:
        candidates = (
            list(entries) if entries is not None else self.store.list_entries(status="active")
        )
        requested_type = MemoryType(memory_type) if memory_type is not None else None
        candidates = [
            entry
            for entry in candidates
            if entry.status == "active"
            and entry.superseded_by is None
            and (requested_type is None or entry.type == requested_type)
            and (branch is None or entry.branch == branch)
        ]
        candidates.sort(key=lambda entry: entry.id)
        clusters = self._clusters(candidates)
        consolidated: list[MemoryEntry] = []
        superseded_ids: list[str] = []
        skipped = 0
        used_adapter = False
        prepared: list[tuple[MemoryEntry, list[MemoryEntry]]] = []
        for cluster in clusters:
            if len(cluster) < self.min_cluster_size:
                skipped += 1
                continue
            content, llm_used = self._summary(cluster)
            used_adapter = used_adapter or llm_used
            source_ids = [entry.id for entry in cluster]
            dominant_type = self._dominant_type(cluster)
            confidence = sum(self.store.aged_confidence(entry) for entry in cluster) / len(cluster)
            branches = {entry.branch for entry in cluster}
            identifier = stable_id("mem", "consolidation", *source_ids)
            consolidated_entry = MemoryEntry(
                id=identifier,
                type=dominant_type,
                content=content,
                summary=f"Consolidated from {len(cluster)} memories",
                tags=sorted({tag for entry in cluster for tag in entry.tags}),
                related_node_ids=sorted(
                    {node_id for entry in cluster for node_id in entry.related_node_ids}
                ),
                confidence=confidence,
                initial_confidence=confidence,
                last_verified=utc_now(),
                branch=branches.pop() if len(branches) == 1 else None,
                source=f"consolidation:{'llm' if llm_used else 'deterministic'}",
            )
            prepared.append((consolidated_entry, cluster))

        if prepared:
            with self.store.database.transaction(immediate=True) as connection:
                for consolidated_entry, cluster in prepared:
                    existing = connection.execute(
                        "SELECT id FROM memories WHERE id = ?", (consolidated_entry.id,)
                    ).fetchone()
                    if existing is None:
                        self.store._insert(connection, consolidated_entry)
                    else:
                        self.store._replace(connection, consolidated_entry)
                    consolidated.append(consolidated_entry)
                    for original in cluster:
                        connection.execute(
                            """
                            UPDATE memories
                            SET superseded_by = ?, status = 'superseded'
                            WHERE id = ? AND id != ?
                            """,
                            (consolidated_entry.id, original.id, consolidated_entry.id),
                        )
                        superseded_ids.append(original.id)
                Database.bump_index_revision(connection)
        return ConsolidationResult(
            consolidated=consolidated,
            superseded_ids=sorted(set(superseded_ids)),
            skipped_clusters=skipped,
            capability_mode="llm_enhanced" if used_adapter else "deterministic",
        )

    def _summary(self, cluster: Sequence[MemoryEntry]) -> tuple[str, bool]:
        if self.adapter is not None:
            try:
                summary = self.adapter.consolidate(tuple(cluster)).strip()
            except Exception:
                summary = ""
            if summary:
                return summary, True
        # Stable order and explicit source labels make deterministic output reviewable.
        lines = [
            f"- [{entry.id}] {entry.summary or entry.content.strip()}"
            for entry in sorted(cluster, key=lambda value: value.id)
        ]
        return "Consolidated knowledge:\n" + "\n".join(lines), False

    def _clusters(self, entries: Sequence[MemoryEntry]) -> list[list[MemoryEntry]]:
        parent = list(range(len(entries)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        for left in range(len(entries)):
            for right in range(left + 1, len(entries)):
                if self._related(entries[left], entries[right]):
                    union(left, right)
        grouped: dict[int, list[MemoryEntry]] = {}
        for index, entry in enumerate(entries):
            grouped.setdefault(find(index), []).append(entry)
        return [grouped[key] for key in sorted(grouped)]

    def _related(self, left: MemoryEntry, right: MemoryEntry) -> bool:
        if left.type != right.type:
            return False
        if left.branch != right.branch:
            return False
        if set(left.tags).intersection(right.tags):
            return True
        if set(left.related_node_ids).intersection(right.related_node_ids):
            return True
        left_terms = set(tokenize(f"{left.summary or ''} {left.content}"))
        right_terms = set(tokenize(f"{right.summary or ''} {right.content}"))
        if not left_terms or not right_terms:
            return False
        similarity = len(left_terms & right_terms) / len(left_terms | right_terms)
        return similarity >= self.lexical_threshold

    @staticmethod
    def _dominant_type(entries: Sequence[MemoryEntry]) -> MemoryType:
        counts = Counter(entry.type for entry in entries)
        return min(counts, key=lambda kind: (-counts[kind], kind.value))


def consolidate_memory(
    store: MemoryStore,
    *,
    adapter: ConsolidationAdapter | None = None,
    min_cluster_size: int | None = None,
    memory_type: MemoryType | str | None = None,
    branch: str | None = None,
) -> ConsolidationResult:
    """Functional facade used by MCP/CLI adapters."""

    return DeterministicConsolidator(
        store,
        adapter=adapter,
        min_cluster_size=min_cluster_size,
    ).consolidate(memory_type=memory_type, branch=branch)
