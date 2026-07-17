"""Revision-keyed persistent cache for fully assembled context bundles."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime

from pydantic import ValidationError

from projectmind.database import Database
from projectmind.models.common import utc_now
from projectmind.models.retrieval_models import ContextBundle


class ContextCache:
    """Cache entries are reusable only at the exact current index revision."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def key(
        task: str,
        *,
        mode: str,
        token_budget: int,
        include_memory: bool,
        depth: int,
        branch: str | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> str:
        payload = {
            "task": " ".join(task.casefold().split()),
            "mode": mode,
            "token_budget": token_budget,
            "include_memory": include_memory,
            "depth": depth,
            "branch": branch,
            "extra": dict(sorted((extra or {}).items())),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def get(self, cache_key: str, *, index_revision: int | None = None) -> ContextBundle | None:
        revision = self.database.index_revision() if index_revision is None else index_revision
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT index_revision, result_json FROM context_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None or int(row["index_revision"]) != revision:
            return None
        try:
            bundle = ContextBundle.model_validate_json(str(row["result_json"]))
        except (ValidationError, ValueError):
            self.delete(cache_key)
            return None
        return bundle.model_copy(update={"cache_hit": True})

    def put(
        self,
        cache_key: str,
        bundle: ContextBundle,
        *,
        index_revision: int | None = None,
        created_at: datetime | None = None,
    ) -> None:
        revision = self.database.index_revision() if index_revision is None else index_revision
        stored = bundle.model_copy(update={"cache_hit": False})
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO context_cache(cache_key, index_revision, result_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    index_revision = excluded.index_revision,
                    result_json = excluded.result_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    revision,
                    stored.model_dump_json(),
                    (created_at or utc_now()).isoformat(),
                ),
            )

    set = put

    def delete(self, cache_key: str) -> bool:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "DELETE FROM context_cache WHERE cache_key = ?", (cache_key,)
            )
        return cursor.rowcount > 0

    def prune_stale(self, *, current_revision: int | None = None) -> int:
        revision = self.database.index_revision() if current_revision is None else current_revision
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                "DELETE FROM context_cache WHERE index_revision != ?", (revision,)
            )
        return cursor.rowcount
