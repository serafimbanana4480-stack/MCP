from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDES = {
    ".git",
    ".projectmind",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
}


@dataclass
class Config:
    root: Path
    db_path: Path
    excludes: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDES))
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "graph_relevance": 0.35,
            "semantic_similarity": 0.25,
            "lexical_match": 0.20,
            "recency_git": 0.10,
            "architectural_importance": 0.10,
        }
    )
    allowed_commands: set[str] = field(
        default_factory=lambda: {"python", "pytest", "ruff", "mypy", "git", "npm", "pnpm", "yarn"}
    )
    command_timeout: int = 30
    allow_write: bool = True

    @classmethod
    def load(cls, root: str | Path = ".") -> Config:
        root_path = Path(root).expanduser().resolve()
        data: dict[str, Any] = {}
        for candidate in (
            root_path / "projectmind.toml",
            root_path / ".projectmind" / "config.toml",
        ):
            if candidate.exists():
                with candidate.open("rb") as fh:
                    data.update(tomllib.load(fh))
        project = data.get("project", {})
        db = Path(project.get("db_path", ".projectmind/projectmind.sqlite3"))
        db_path = db if db.is_absolute() else root_path / db
        retrieval = data.get("retrieval", {})
        weights = {
            k: float(retrieval.get(k, v)) for k, v in cls(root_path, db_path).weights.items()
        }
        security = data.get("security", {})
        return cls(
            root_path,
            db_path,
            set(project.get("exclude", DEFAULT_EXCLUDES)),
            weights,
            set(security.get("allowed_commands", cls(root_path, db_path).allowed_commands)),
            int(security.get("command_timeout", 30)),
            bool(security.get("allow_write", True)),
        )

    def safe_path(self, path: str | Path) -> Path:
        candidate = (
            (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        )
        candidate.relative_to(self.root)
        return candidate
