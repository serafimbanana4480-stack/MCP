"""Deterministic, bounded source-file discovery.

Discovery deliberately does not try to identify generated code by inspecting its
contents.  It only applies explicit path rules, supported extensions and a size
limit, which makes the result predictable and safe on large repositories.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".projectmind",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "**/*.min.js",
    "**/*.min.css",
)


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """A source file accepted for indexing."""

    path: Path
    relative_path: str
    language: str
    size_bytes: int
    mtime_ns: int


def detect_language(path: Path | str) -> str | None:
    """Return the canonical language name for a supported filename."""

    return LANGUAGE_EXTENSIONS.get(Path(path).suffix.lower())


class FileDiscovery:
    """Walk a project without following directory symlinks or escaping its root."""

    def __init__(
        self,
        root: Path | str,
        *,
        excludes: Iterable[str] = DEFAULT_EXCLUDES,
        max_file_bytes: int = 2_000_000,
        languages: Iterable[str] | None = None,
    ) -> None:
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        self.root = Path(root).resolve()
        self.excludes = tuple(self._normalise_pattern(pattern) for pattern in excludes)
        self.max_file_bytes = max_file_bytes
        self.languages = frozenset(item.lower() for item in languages or ())

    @staticmethod
    def _normalise_pattern(pattern: str) -> str:
        value = pattern.strip().replace("\\", "/")
        if value.startswith("./"):
            value = value[2:]
        return value.rstrip("/")

    def _is_excluded(self, relative_path: str, *, is_dir: bool = False) -> bool:
        candidate = relative_path.replace("\\", "/").strip("/")
        if not candidate:
            return False
        parts = PurePosixPath(candidate).parts
        basename = parts[-1]
        for pattern in self.excludes:
            if not pattern:
                continue
            # A plain name excludes that path component at any depth.  Glob
            # patterns are checked against both the full relative path and name.
            if not any(char in pattern for char in "*?["):
                if pattern in parts or candidate == pattern or candidate.startswith(f"{pattern}/"):
                    return True
                continue
            if fnmatch.fnmatchcase(candidate, pattern) or fnmatch.fnmatchcase(basename, pattern):
                return True
            # Python's fnmatch treats ``**/x`` as requiring a slash.  Also test
            # the pattern without that prefix so root-level files behave as users expect.
            if pattern.startswith("**/") and fnmatch.fnmatchcase(candidate, pattern[3:]):
                return True
            if is_dir and fnmatch.fnmatchcase(f"{candidate}/", pattern.rstrip("/") + "/"):
                return True
        return False

    def discover(self, scope: Path | str | None = None) -> list[DiscoveredFile]:
        """Return accepted files sorted by POSIX relative path.

        A missing scope returns an empty list.  A scope outside the project is
        rejected, including a symlink whose resolved target leaves the project.
        """

        start = self.root if scope is None else Path(scope)
        if not start.is_absolute():
            start = self.root / start
        start = start.resolve()
        try:
            start.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"scope is outside project root: {start}") from exc
        if not start.exists():
            return []

        candidates: Iterator[Path] = iter((start,)) if start.is_file() else self._walk(start)

        found: list[DiscoveredFile] = []
        for path in candidates:
            try:
                resolved = path.resolve()
                relative = resolved.relative_to(self.root).as_posix()
            except (OSError, ValueError):
                continue
            if self._is_excluded(relative):
                continue
            language = detect_language(resolved)
            if language is None or (self.languages and language not in self.languages):
                continue
            try:
                stat = resolved.stat()
            except OSError:
                continue
            if not resolved.is_file() or stat.st_size > self.max_file_bytes:
                continue
            found.append(
                DiscoveredFile(
                    path=resolved,
                    relative_path=relative,
                    language=language,
                    size_bytes=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )
            )
        return sorted(found, key=lambda item: item.relative_path)

    def _walk(self, start: Path) -> Iterator[Path]:
        for current, directory_names, file_names in os.walk(start, followlinks=False):
            current_path = Path(current)
            kept: list[str] = []
            for name in sorted(directory_names):
                directory = current_path / name
                if directory.is_symlink():
                    continue
                try:
                    relative = directory.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                if not self._is_excluded(relative, is_dir=True):
                    kept.append(name)
            directory_names[:] = kept
            for name in sorted(file_names):
                path = current_path / name
                if not path.is_symlink():
                    yield path


def discover_source_files(
    root: Path | str,
    *,
    scope: Path | str | None = None,
    excludes: Iterable[str] = DEFAULT_EXCLUDES,
    max_file_bytes: int = 2_000_000,
    languages: Iterable[str] | None = None,
) -> list[DiscoveredFile]:
    """Functional facade for :class:`FileDiscovery`."""

    return FileDiscovery(
        root,
        excludes=excludes,
        max_file_bytes=max_file_bytes,
        languages=languages,
    ).discover(scope)


__all__ = [
    "DEFAULT_EXCLUDES",
    "LANGUAGE_EXTENSIONS",
    "DiscoveredFile",
    "FileDiscovery",
    "detect_language",
    "discover_source_files",
]
