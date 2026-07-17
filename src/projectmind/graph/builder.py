"""Graph construction coordinator."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from projectmind.database import Database
from projectmind.graph.store import GraphStore

if TYPE_CHECKING:
    from projectmind.indexing.extractor import ExtractionResult


class GraphBuilder:
    """Persist extractor output through one atomic, idempotent code path."""

    def __init__(self, store: GraphStore | Database) -> None:
        self.store = store if isinstance(store, GraphStore) else GraphStore(store)

    def build(self, extraction: ExtractionResult, *, force: bool = False) -> bool:
        return self.store.replace_file(extraction, force=force)

    def build_many(
        self,
        extractions: Iterable[ExtractionResult],
        *,
        remove_paths: Iterable[str | Path] = (),
        force: bool = False,
    ) -> list[str]:
        return self.store.replace_files(
            extractions,
            remove_paths=remove_paths,
            force=force,
        )

    persist = build
    persist_many = build_many


__all__ = ["GraphBuilder"]
