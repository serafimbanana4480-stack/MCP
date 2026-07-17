"""Rules for combining project-wide and current-branch memories."""

from __future__ import annotations

from collections.abc import Iterable

DEFAULT_GLOBAL_BRANCHES = frozenset({"main", "master"})


def normalize_branch(branch: str | None) -> str | None:
    """Return a stable branch name, treating blank values as project-wide."""

    if branch is None:
        return None
    normalized = branch.strip()
    return normalized or None


def branch_is_visible(
    entry_branch: str | None,
    current_branch: str | None,
    *,
    include_global: bool = True,
    global_branches: Iterable[str] = DEFAULT_GLOBAL_BRANCHES,
) -> bool:
    """Whether a memory belongs in a branch-aware query.

    ``None`` is explicitly project-wide. ``main`` and ``master`` are also treated
    as global by default so feature branches can inherit established decisions.
    A query without a current branch deliberately returns only global knowledge.
    """

    entry = normalize_branch(entry_branch)
    current = normalize_branch(current_branch)
    globals_ = {value for item in global_branches if (value := normalize_branch(item))}
    if current is not None and entry == current:
        return True
    if not include_global:
        return current is None and entry is None
    return entry is None or entry in globals_
