"""Explicit creation of reversible ProjectMind-owned state under `.projectmind`."""

from __future__ import annotations

import secrets
from pathlib import Path

from projectmind.config import default_config_toml
from projectmind.database import Database


def initialize_project_state(
    project_root: Path, *, overwrite_config: bool = False
) -> dict[str, str]:
    root = project_root.resolve()
    state_dir = root / ".projectmind"
    state_dir.mkdir(parents=True, exist_ok=True)
    config_path = state_dir / "config.toml"
    if config_path.exists() and overwrite_config:
        config_path.write_text(default_config_toml(root.name), encoding="utf-8")
    if not config_path.exists():
        config_path.write_text(default_config_toml(root.name), encoding="utf-8")
    token_path = state_dir / "http-token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    database_path = state_dir / "projectmind.db"
    Database(database_path, root).initialize()
    return {
        "project_root": str(root),
        "config": str(config_path),
        "database": str(database_path),
        "http_token": str(token_path),
    }

