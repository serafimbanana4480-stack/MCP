"""Project source discovery and indexing."""

from projectmind.indexing.discovery import (
    DiscoveredFile,
    FileDiscovery,
    detect_language,
    discover_source_files,
)
from projectmind.indexing.extractor import (
    CodeExtractor,
    ExtractedChunk,
    ExtractionResult,
    Extractor,
    extract_file,
)
from projectmind.indexing.git_intelligence import GitIntelligence, SymbolDiff
from projectmind.indexing.indexer import (
    IndexingReport,
    ProjectIndexer,
    index_scope,
    reindex_on_git_pull,
)
from projectmind.indexing.monorepo_detector import (
    MonorepoDetector,
    Workspace,
    detect_workspaces,
)
from projectmind.indexing.watcher import IncrementalWatcher, ProjectWatcher, watch_project

__all__ = [
    "CodeExtractor",
    "DiscoveredFile",
    "ExtractedChunk",
    "ExtractionResult",
    "Extractor",
    "FileDiscovery",
    "GitIntelligence",
    "IncrementalWatcher",
    "IndexingReport",
    "MonorepoDetector",
    "ProjectIndexer",
    "ProjectWatcher",
    "SymbolDiff",
    "Workspace",
    "detect_language",
    "detect_workspaces",
    "discover_source_files",
    "extract_file",
    "index_scope",
    "reindex_on_git_pull",
    "watch_project",
]
