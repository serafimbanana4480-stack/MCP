"""Root-confined path resolution shared by execution capabilities."""

from __future__ import annotations

from pathlib import Path

from projectmind.errors import SecurityError

PROTECTED_TOP_LEVEL = {".git"}


def resolve_project_path(
    project_root: Path,
    relative_path: str | Path,
    *,
    allow_root: bool = False,
) -> Path:
    """Resolve a user path while rejecting absolute, traversal, and symlink escapes."""

    root = project_root.resolve()
    raw = Path(relative_path)
    if raw.is_absolute():
        raise SecurityError("absolute paths are not allowed")
    if not raw.parts or (len(raw.parts) == 1 and raw.parts[0] in {"", "."}):
        if allow_root:
            return root
        raise SecurityError("a file or subdirectory path is required")
    if any(part == ".." for part in raw.parts):
        raise SecurityError("parent traversal is not allowed")
    if raw.parts[0].casefold() in {part.casefold() for part in PROTECTED_TOP_LEVEL}:
        raise SecurityError(f"protected path cannot be mutated: {raw.parts[0]}")

    candidate = (root / raw).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SecurityError("path resolves outside the project root") from exc
    if candidate == root and not allow_root:
        raise SecurityError("project root is not a valid file target")
    return candidate


def relative_to_root(project_root: Path, resolved_path: Path) -> str:
    return resolved_path.resolve(strict=False).relative_to(project_root.resolve()).as_posix()

