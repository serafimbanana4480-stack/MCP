from pathlib import Path

from ..core.config import Config
from ..core.db import Database
from .scanner import scan


def index_changed(config: Config, db: Database, paths: list[str]) -> dict[str, object]:
    return scan(config, db, scope=str(Path(paths[0]).parent) if paths else None, incremental=True)
