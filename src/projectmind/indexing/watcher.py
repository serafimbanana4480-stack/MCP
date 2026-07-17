"""Cancellable incremental indexing helper built on watchfiles."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from projectmind.indexing.discovery import FileDiscovery, detect_language
from projectmind.models.graph_models import GraphSummary


class Reindexer(Protocol):
    root: Path

    def reindex_paths(
        self, paths: Iterable[Path | str], *, include_dependents: bool = True
    ) -> GraphSummary: ...


class IncrementalWatcher:
    def __init__(self, indexer: Reindexer, *, debounce_ms: int = 150) -> None:
        if debounce_ms < 0:
            raise ValueError("debounce_ms cannot be negative")
        self.indexer = indexer
        self.root = indexer.root.resolve()
        self.debounce_ms = debounce_ms
        config = getattr(indexer, "config", None)
        self.excludes = tuple(getattr(config, "exclude", (".git", ".projectmind", "node_modules")))
        max_file_bytes = int(getattr(config, "max_file_bytes", 2_000_000))
        self.discovery = FileDiscovery(
            self.root,
            excludes=self.excludes,
            max_file_bytes=max_file_bytes,
        )
        database = getattr(indexer, "database", None)
        self.database_path = getattr(database, "path", None)

    def filter_paths(self, changes: Iterable[object]) -> list[str]:
        accepted: set[str] = set()
        database_paths: set[Path] = set()
        if self.database_path is not None:
            db = Path(self.database_path).resolve()
            database_paths = {db, Path(str(db) + "-wal"), Path(str(db) + "-shm")}
        for change in changes:
            raw_path: object = (
                change[1] if isinstance(change, tuple) and len(change) >= 2 else change
            )
            try:
                path = Path(str(raw_path)).resolve()
                relative = path.relative_to(self.root).as_posix()
            except (OSError, ValueError):
                continue
            if path in database_paths:
                continue
            if self.discovery._is_excluded(relative):
                continue
            if detect_language(relative) is None:
                continue
            accepted.add(relative)
        return sorted(accepted)

    def process_changes(self, changes: Iterable[object]) -> GraphSummary | None:
        paths = self.filter_paths(changes)
        if not paths:
            return None
        return self.indexer.reindex_paths(paths, include_dependents=True)

    def impacted_paths(self, changes: Iterable[object]) -> list[str]:
        """Preview changed paths plus their currently indexed direct dependents."""

        paths = self.filter_paths(changes)
        store = getattr(self.indexer, "store", None)
        if store is None or not hasattr(store, "dependent_paths"):
            return paths
        dependents = store.dependent_paths(paths)
        return sorted(set(paths) | set(dependents))

    async def watch(self, *, stop_event: object | None = None) -> None:
        """Run until cancelled or ``stop_event`` is set."""

        try:
            from watchfiles import awatch
        except ImportError as exc:  # pragma: no cover - declared runtime dependency
            raise RuntimeError("watchfiles is required for filesystem watching") from exc
        async for changes in awatch(
            self.root,
            debounce=self.debounce_ms,
            stop_event=stop_event,
            recursive=True,
        ):
            self.process_changes(changes)

    run = watch


ProjectWatcher = IncrementalWatcher


async def watch_project(
    indexer: Reindexer,
    *,
    debounce_ms: int = 150,
    stop_event: object | None = None,
) -> None:
    await IncrementalWatcher(indexer, debounce_ms=debounce_ms).watch(stop_event=stop_event)


__all__ = ["IncrementalWatcher", "ProjectWatcher", "Reindexer", "watch_project"]
