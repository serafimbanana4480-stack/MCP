"""Git-aware changed-file and changed-symbol inspection."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from projectmind.graph.store import GraphStore
from projectmind.models.graph_models import NodeType


@dataclass(frozen=True, slots=True)
class DiffHunk:
    path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    @property
    def new_end(self) -> int:
        return self.new_start + max(1, self.new_count) - 1


@dataclass(frozen=True, slots=True)
class ChangedSymbol:
    node_id: str
    path: str
    qualname: str
    node_type: str
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True, slots=True)
class SymbolDiff:
    files: tuple[str, ...]
    hunks: tuple[DiffHunk, ...]
    symbols: tuple[ChangedSymbol, ...]
    raw_diff: str = ""
    available: bool = True
    warning: str | None = None

    @property
    def changed_symbols(self) -> tuple[ChangedSymbol, ...]:
        return self.symbols


def parse_unified_diff(diff_text: str) -> tuple[DiffHunk, ...]:
    hunks: list[DiffHunk] = []
    current_path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            value = line[4:].split("\t", 1)[0]
            current_path = None if value == "/dev/null" else value.removeprefix("b/")
            continue
        match = re.match(
            r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@",
            line,
        )
        if match and current_path:
            hunks.append(
                DiffHunk(
                    path=current_path,
                    old_start=int(match.group(1)),
                    old_count=int(match.group(2) or "1"),
                    new_start=int(match.group(3)),
                    new_count=int(match.group(4) or "1"),
                )
            )
    return tuple(hunks)


class GitIntelligence:
    def __init__(self, root: Path | str, store: GraphStore | None = None) -> None:
        self.root = Path(root).resolve()
        self.store = store

    def _git(
        self, arguments: list[str], *, timeout: float = 10.0
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )

    def is_repository(self) -> bool:
        try:
            result = self._git(["rev-parse", "--is-inside-work-tree"])
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and result.stdout.strip() == "true"

    def diff(
        self,
        base_ref: str | None = None,
        head_ref: str | None = None,
        *,
        staged: bool = False,
    ) -> str:
        arguments = ["diff", "--no-ext-diff", "--unified=0"]
        if staged:
            arguments.append("--cached")
        if base_ref and head_ref:
            self._validate_ref(base_ref)
            self._validate_ref(head_ref)
            arguments.extend([base_ref, head_ref])
        elif base_ref:
            self._validate_ref(base_ref)
            arguments.append(base_ref)
        arguments.append("--")
        try:
            result = self._git(arguments)
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout if result.returncode == 0 else ""

    def changed_files(
        self,
        base_ref: str | None = None,
        head_ref: str | None = None,
        *,
        staged: bool = False,
    ) -> list[str]:
        arguments = ["diff", "--name-only", "--diff-filter=ACDMRTUXB"]
        if staged:
            arguments.append("--cached")
        if base_ref and head_ref:
            self._validate_ref(base_ref)
            self._validate_ref(head_ref)
            arguments.extend([base_ref, head_ref])
        elif base_ref:
            self._validate_ref(base_ref)
            arguments.append(base_ref)
        arguments.append("--")
        try:
            result = self._git(arguments)
        except (OSError, subprocess.SubprocessError):
            return []
        if result.returncode != 0:
            return []
        return sorted(
            {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
        )

    @staticmethod
    def _validate_ref(reference: str) -> None:
        if (
            not reference
            or reference.startswith("-")
            or not re.fullmatch(r"[A-Za-z0-9_./@{}~^:+-]+", reference)
        ):
            raise ValueError(f"invalid Git revision: {reference!r}")

    def symbol_diff(
        self,
        base_ref: str | None = None,
        head_ref: str | None = None,
        *,
        diff_text: str | None = None,
        staged: bool = False,
    ) -> SymbolDiff:
        if self.store is None:
            raise ValueError("symbol_diff requires a GraphStore")
        available = self.is_repository() if diff_text is None else True
        raw = diff_text if diff_text is not None else self.diff(base_ref, head_ref, staged=staged)
        hunks = parse_unified_diff(raw)
        files = sorted({hunk.path for hunk in hunks})
        if not files and diff_text is None:
            files = self.changed_files(base_ref, head_ref, staged=staged)
        symbols: dict[str, ChangedSymbol] = {}
        for path in files:
            path_hunks = [hunk for hunk in hunks if hunk.path == path]
            candidates = self.store.nodes(scope=path)
            for node in candidates:
                if node.path != path:
                    continue
                intersects = node.type is NodeType.FILE or not path_hunks
                if node.start_line is not None and node.end_line is not None:
                    intersects = any(
                        node.start_line <= hunk.new_end and node.end_line >= hunk.new_start
                        for hunk in path_hunks
                    )
                if intersects:
                    symbols[node.id] = ChangedSymbol(
                        node_id=node.id,
                        path=node.path,
                        qualname=node.qualname,
                        node_type=node.type.value,
                        start_line=node.start_line,
                        end_line=node.end_line,
                    )
        return SymbolDiff(
            files=tuple(files),
            hunks=hunks,
            symbols=tuple(
                sorted(
                    symbols.values(),
                    key=lambda item: (item.path, item.start_line or 0, item.node_id),
                )
            ),
            raw_diff=raw,
            available=available,
            warning=None if available else "not a Git repository or Git is unavailable",
        )

    def files_changed_on_pull(
        self, old_head: str | None = None, new_head: str = "HEAD"
    ) -> list[str]:
        base = old_head or "HEAD@{1}"
        return self.changed_files(base, new_head)

    def co_change_counts(self, max_commits: int = 200) -> dict[tuple[str, str], int]:
        if max_commits < 1:
            return {}
        try:
            result = self._git(
                ["log", f"-n{max_commits}", "--name-only", "--pretty=format:__PM_COMMIT__"]
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0:
            return {}
        counts: Counter[tuple[str, str]] = Counter()
        current: set[str] = set()

        def consume() -> None:
            ordered = sorted(current)
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    counts[(left, right)] += 1

        for line in result.stdout.splitlines():
            value = line.strip().replace("\\", "/")
            if value == "__PM_COMMIT__":
                consume()
                current.clear()
            elif value:
                current.add(value)
        consume()
        return dict(sorted(counts.items()))


GitSymbolDiff = SymbolDiff


__all__ = [
    "ChangedSymbol",
    "DiffHunk",
    "GitIntelligence",
    "GitSymbolDiff",
    "SymbolDiff",
    "parse_unified_diff",
]
