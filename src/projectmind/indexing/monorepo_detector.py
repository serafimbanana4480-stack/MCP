"""Logical workspace detection for polyglot repositories."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from projectmind.models.common import stable_id

from .discovery import DEFAULT_EXCLUDES

MANIFEST_KINDS: dict[str, str] = {
    "package.json": "node",
    "pyproject.toml": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java-maven",
    "build.gradle": "java-gradle",
    "build.gradle.kts": "java-gradle",
}


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    path: str
    kind: str
    name: str
    manifest: str
    metadata: dict[str, object] = field(default_factory=dict)


def _manifest_name(path: Path, kind: str) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return path.parent.name or "root"
    if kind == "node":
        try:
            value = json.loads(text).get("name")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except (json.JSONDecodeError, AttributeError):
            pass
    elif kind == "go":
        match = re.search(r"(?m)^\s*module\s+([^\s]+)", text)
        if match:
            return match.group(1)
    elif kind == "rust":
        package = re.search(r"(?ms)^\s*\[package\].*?^\s*name\s*=\s*['\"]([^'\"]+)", text)
        if package:
            return package.group(1)
    elif kind == "python":
        project = re.search(r"(?ms)^\s*\[project\].*?^\s*name\s*=\s*['\"]([^'\"]+)", text)
        poetry = re.search(r"(?ms)^\s*\[tool\.poetry\].*?^\s*name\s*=\s*['\"]([^'\"]+)", text)
        match = project if project is not None else poetry
        if match is not None:
            return match.group(1)
    elif kind.startswith("java"):
        match = re.search(r"<artifactId>\s*([^<]+)\s*</artifactId>", text)
        if not match:
            match = re.search(r"(?m)^\s*rootProject\.name\s*=\s*['\"]([^'\"]+)", text)
        if match:
            return match.group(1).strip()
    return path.parent.name or "root"


class MonorepoDetector:
    def __init__(self, root: Path | str, excludes: tuple[str, ...] = DEFAULT_EXCLUDES) -> None:
        self.root = Path(root).resolve()
        self.excluded_names = frozenset(
            pattern for pattern in excludes if not any(char in pattern for char in "*?[")
        )

    def detect(self) -> list[Workspace]:
        manifests: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.name not in MANIFEST_KINDS:
                continue
            try:
                relative = path.relative_to(self.root)
            except ValueError:
                continue
            if any(part in self.excluded_names for part in relative.parts):
                continue
            manifests.append(path)

        # The database models one logical workspace per path.  A polyglot root
        # can have several manifests, so keep them together in metadata rather
        # than violating the unique path constraint.
        grouped: dict[str, list[Path]] = {}
        for manifest in manifests:
            relative_dir = manifest.parent.relative_to(self.root).as_posix()
            grouped.setdefault("." if relative_dir == "." else relative_dir, []).append(manifest)
        workspaces: list[Workspace] = []
        for relative_dir, directory_manifests in sorted(grouped.items()):
            ordered_manifests = sorted(
                directory_manifests, key=lambda item: item.relative_to(self.root).as_posix()
            )
            manifest = ordered_manifests[0]
            kinds = sorted({MANIFEST_KINDS[item.name] for item in ordered_manifests})
            kind = kinds[0] if len(kinds) == 1 else "polyglot"
            relative_manifest = manifest.relative_to(self.root).as_posix()
            manifest_paths = [item.relative_to(self.root).as_posix() for item in ordered_manifests]
            workspaces.append(
                Workspace(
                    id=stable_id("workspace", relative_dir),
                    path=relative_dir,
                    kind=kind,
                    name=_manifest_name(manifest, MANIFEST_KINDS[manifest.name]),
                    manifest=relative_manifest,
                    metadata={
                        "manifest": relative_manifest,
                        "manifests": manifest_paths,
                        "kinds": kinds,
                    },
                )
            )
        return workspaces

    def is_monorepo(self) -> bool:
        workspaces = self.detect()
        logical_roots = {item.path for item in workspaces}
        return len(logical_roots) > 1


def detect_workspaces(root: Path | str) -> list[Workspace]:
    return MonorepoDetector(root).detect()


__all__ = ["MANIFEST_KINDS", "MonorepoDetector", "Workspace", "detect_workspaces"]
