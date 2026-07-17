"""Local telemetry persistence and aggregate usage statistics."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from projectmind.config import ProjectMindSettings
from projectmind.database import Database
from projectmind.models.common import new_id, utc_now


class TelemetryStore:
    def __init__(self, database: Database, settings: ProjectMindSettings) -> None:
        self.database = database
        self.settings = settings

    def record(
        self,
        tool_name: str,
        *,
        success: bool,
        latency_ms: int,
        tokens_used: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if not self.settings.telemetry.enabled:
            return
        safe_metadata = self._anonymize(metadata or {})
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO telemetry_events(
                    id, tool_name, timestamp, tokens_used, success, latency_ms, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("evt"),
                    tool_name,
                    utc_now().isoformat(),
                    tokens_used,
                    int(success),
                    max(0, latency_ms),
                    json.dumps(safe_metadata, sort_keys=True),
                ),
            )

    @contextmanager
    def measure(self, tool_name: str, **metadata: object) -> Iterator[dict[str, object]]:
        started = perf_counter()
        outcome: dict[str, object] = {"success": True, "tokens_used": None}
        try:
            yield outcome
        except Exception:
            outcome["success"] = False
            raise
        finally:
            self.record(
                tool_name,
                success=bool(outcome.get("success", True)),
                latency_ms=round((perf_counter() - started) * 1_000),
                tokens_used=(
                    int(tokens_val)
                    if (tokens_val := outcome.get("tokens_used")) is not None
                    and isinstance(tokens_val, int)
                    else None
                ),
                metadata=metadata,
            )

    def usage_stats(self) -> dict[str, object]:
        with self.database.connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*) AS calls,
                       COALESCE(SUM(success), 0) AS successes,
                       COALESCE(SUM(tokens_used), 0) AS tokens_used,
                       COALESCE(AVG(latency_ms), 0) AS average_latency_ms
                FROM telemetry_events
                """
            ).fetchone()
            tools = connection.execute(
                """
                SELECT tool_name, COUNT(*) AS calls, SUM(success) AS successes,
                       ROUND(AVG(latency_ms), 2) AS average_latency_ms
                FROM telemetry_events
                GROUP BY tool_name
                ORDER BY calls DESC, tool_name
                """
            ).fetchall()
        calls = int(totals["calls"])
        successes = int(totals["successes"])
        return {
            "calls": calls,
            "successes": successes,
            "success_rate": successes / calls if calls else 0.0,
            "tokens_used": int(totals["tokens_used"]),
            "average_latency_ms": float(totals["average_latency_ms"]),
            "tools": [dict(row) for row in tools],
        }

    def _anonymize(self, metadata: dict[str, object]) -> dict[str, object]:
        if not self.settings.telemetry.anonymized:
            return metadata
        safe: dict[str, object] = {}
        for key, value in metadata.items():
            if any(
                term in key.casefold()
                for term in ("path", "query", "task", "content", "error")
            ):
                digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
                safe[f"{key}_hash"] = digest
            elif isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
        return safe

