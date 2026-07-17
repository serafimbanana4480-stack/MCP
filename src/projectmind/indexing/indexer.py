"""High-level project indexing coordinator."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from projectmind.config import IndexingConfig, ProjectMindSettings
from projectmind.database import Database
from projectmind.graph.builder import GraphBuilder
from projectmind.graph.store import GraphStore
from projectmind.indexing.discovery import DiscoveredFile, FileDiscovery
from projectmind.indexing.extractor import Extractor
from projectmind.indexing.git_intelligence import GitIntelligence
from projectmind.indexing.monorepo_detector import MonorepoDetector
from projectmind.models.graph_models import GraphSummary


@dataclass(frozen=True, slots=True)
class IndexingReport:
    summary: GraphSummary
    discovered: int
    indexed_paths: tuple[str, ...]
    skipped_paths: tuple[str, ...]
    removed_paths: tuple[str, ...]
    workspaces: int
    warnings: tuple[str, ...] = ()


class ProjectIndexer:
    """Discover, extract and atomically persist project source."""

    def __init__(
        self,
        root: Path | str,
        database: Database | None = None,
        *,
        database_path: Path | str | None = None,
        config: IndexingConfig | ProjectMindSettings | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        if isinstance(config, ProjectMindSettings):
            indexing_config = config.indexing
        else:
            indexing_config = config or IndexingConfig()
        self.config = indexing_config
        if database_path is None:
            selected_path = self.root / ".projectmind" / "projectmind.db"
        else:
            selected_path = Path(database_path)
            if not selected_path.is_absolute():
                selected_path = self.root / selected_path
        self.database = database or Database(selected_path, self.root)
        self.database.initialize()
        self.store = GraphStore(self.database)
        self.builder = GraphBuilder(self.store)
        self.discovery = FileDiscovery(
            self.root,
            excludes=self.config.exclude,
            max_file_bytes=self.config.max_file_bytes,
        )
        self.extractor = Extractor(self.root)
        self.git = GitIntelligence(self.root, self.store)
        self.last_report: IndexingReport | None = None

    def index_scope(self, path: Path | str = ".") -> GraphSummary:
        return self.index_scope_report(path).summary

    def index_scope_report(self, path: Path | str = ".") -> IndexingReport:
        scope = self._resolve(path)
        relative_scope = scope.relative_to(self.root).as_posix()
        relative_scope = "." if relative_scope == "." else relative_scope
        discovered = self.discovery.discover(scope)
        existing = set(self.store.file_paths(relative_scope))
        present = {item.relative_path for item in discovered}
        removals = sorted(existing - present)
        extractions = [self.extractor.extract(item) for item in discovered]

        workspace_changed = False
        workspace_count = len(self.store.list_workspaces())
        if scope == self.root:
            workspaces = MonorepoDetector(self.root, tuple(self.config.exclude)).detect()
            workspace_count = len(workspaces)
            workspace_changed = self.store.sync_workspaces(workspaces, bump_revision=False)

        changed = self.builder.build_many(extractions, remove_paths=removals)
        if workspace_changed and not changed:
            self.store.bump_revision()
        indexed = tuple(sorted(path for path in changed if path not in removals))
        skipped = tuple(sorted(present - set(indexed)))
        warnings = tuple(
            f"{item.path}: {warning}" for item in extractions for warning in item.warnings
        )
        report = IndexingReport(
            summary=self.store.summary(relative_scope),
            discovered=len(discovered),
            indexed_paths=indexed,
            skipped_paths=skipped,
            removed_paths=tuple(path for path in changed if path in removals),
            workspaces=workspace_count,
            warnings=warnings,
        )
        self.last_report = report
        return report

    def reindex_paths(
        self, paths: Iterable[Path | str], *, include_dependents: bool = True
    ) -> GraphSummary:
        requested: set[str] = set()
        for value in paths:
            resolved = self._resolve(value)
            relative = resolved.relative_to(self.root).as_posix()
            if resolved.is_dir():
                requested.update(item.relative_path for item in self.discovery.discover(resolved))
                requested.update(self.store.file_paths(relative))
            else:
                indexed_below = self.store.file_paths(relative)
                requested.update(indexed_below or (relative,))
        dependents = set(self.store.dependent_paths(requested)) if include_dependents else set()
        selected = requested | dependents
        discovered_by_path: dict[str, DiscoveredFile] = {}
        removals: set[str] = set()
        stored = set(self.store.file_paths())
        for relative in sorted(selected):
            absolute = self.root / Path(relative)
            found = self.discovery.discover(absolute)
            if found:
                discovered_by_path.update({item.relative_path: item for item in found})
            elif relative in stored:
                removals.add(relative)
        extractions = [
            self.extractor.extract(item)
            for item in sorted(discovered_by_path.values(), key=lambda value: value.relative_path)
        ]
        changed = self.builder.build_many(extractions, remove_paths=removals)
        indexed = tuple(sorted(path for path in changed if path not in removals))
        warnings = tuple(
            f"{item.path}: {warning}" for item in extractions for warning in item.warnings
        )
        self.last_report = IndexingReport(
            summary=self.store.summary(),
            discovered=len(discovered_by_path),
            indexed_paths=indexed,
            skipped_paths=tuple(sorted(set(discovered_by_path) - set(indexed))),
            removed_paths=tuple(sorted(set(changed) & removals)),
            workspaces=len(self.store.list_workspaces()),
            warnings=warnings,
        )
        return self.last_report.summary

    def reindex_on_git_pull(
        self, old_head: str | None = None, new_head: str = "HEAD"
    ) -> GraphSummary:
        changed = self.git.files_changed_on_pull(old_head, new_head)
        return self.reindex_paths(changed) if changed else self.store.summary()

    def get_graph_summary(self, scope: Path | str = ".") -> GraphSummary:
        return self.store.summary(scope)

    def _resolve(self, value: Path | str) -> Path:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"path is outside project root: {value}") from exc
        return resolved


def index_scope(
    root: Path | str,
    path: Path | str = ".",
    *,
    database_path: Path | str | None = None,
) -> GraphSummary:
    return ProjectIndexer(root, database_path=database_path).index_scope(path)


def reindex_on_git_pull(
    root: Path | str,
    *,
    database_path: Path | str | None = None,
    old_head: str | None = None,
    new_head: str = "HEAD",
) -> GraphSummary:
    return ProjectIndexer(root, database_path=database_path).reindex_on_git_pull(old_head, new_head)


__all__ = ["IndexingReport", "ProjectIndexer", "index_scope", "reindex_on_git_pull"]
