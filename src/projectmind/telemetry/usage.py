from __future__ import annotations

import json
import uuid
from typing import Any

PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {
        "input": 0.005,
        "cached_input": 0.00125,
        "output": 0.015,
    },
    "claude-3.5-sonnet": {
        "input": 0.003,
        "cached_input": 0.0003,
        "output": 0.015,
    },
    "local": {
        "input": 0.0,
        "cached_input": 0.0,
        "output": 0.0,
    },
}


def estimate_tokens(text: str) -> int:
    """Estimate token count deterministically: 1 token per ~4 chars (min 1)."""
    return max(1, len(text or "") // 4)


def cost_for(
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Compute USD cost for a single call using real model pricing (per 1K tokens)."""
    rates = PRICING.get(model, PRICING["local"])
    return (
        input_tokens * rates["input"]
        + cached_tokens * rates["cached_input"]
        + output_tokens * rates["output"]
    ) / 1000


class UsageLedger:
    """Records real, deterministic usage metrics into the `usage_ledger` table."""

    def record(
        self,
        db: "Any",
        *,
        action: str,
        model: str = "local",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cache_hit: bool = False,
        ref: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a usage event and return the recorded row as a dict."""
        rates = PRICING.get(model, PRICING["local"])
        cost_usd = round(
            (
                input_tokens * rates["input"]
                + cached_tokens * rates["cached_input"]
                + output_tokens * rates["output"]
            )
            / 1000,
            6,
        )
        event_id = uuid.uuid4().hex
        row = {
            "event_id": event_id,
            "action": action,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cache_hit": int(bool(cache_hit)),
            "cost_usd": cost_usd,
            "ref": ref,
            "payload": json.dumps(payload or {}, default=str),
            "created_at": _now(),
        }
        db.execute(
            """
            INSERT INTO usage_ledger
            (event_id, action, model, input_tokens, output_tokens, cached_tokens,
             cache_hit, cost_usd, ref, payload, created_at)
            VALUES (:event_id, :action, :model, :input_tokens, :output_tokens,
                    :cached_tokens, :cache_hit, :cost_usd, :ref, :payload, :created_at)
            """,
            row,
        )
        return row


class UsageStats:
    """Aggregates real usage metrics from the `usage_ledger` table."""

    @classmethod
    def summary(cls, db: "Any", since: str | None = None) -> dict[str, Any]:
        """Aggregate usage_ledger into totals, cache stats, and breakdowns."""
        where = "WHERE created_at >= ?" if since else ""
        params: tuple[Any, ...] = (since,) if since else ()

        totals = db.one(
            f"""
            SELECT
                COALESCE(SUM(input_tokens), 0)  AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(cached_tokens), 0) AS total_cached_tokens,
                COALESCE(SUM(input_tokens), 0)
                    + COALESCE(SUM(output_tokens), 0)
                    + COALESCE(SUM(cached_tokens), 0) AS total_tokens,
                COALESCE(SUM(cost_usd), 0)      AS total_cost_usd,
                COALESCE(SUM(cache_hit), 0)     AS cache_hits,
                COALESCE(SUM(1 - cache_hit), 0) AS cache_misses,
                COUNT(*)                        AS events
            FROM usage_ledger
            {where}
            """,
            params,
        ) or {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cached_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "events": 0,
        }

        cache_hits = int(totals["cache_hits"])
        cache_misses = int(totals["cache_misses"])
        total_cached = int(totals["total_cached_tokens"])
        cache_hit_rate = (
            cache_hits / (cache_hits + cache_misses)
            if (cache_hits + cache_misses) > 0
            else 0.0
        )

        input_price = PRICING["gpt-4o"]["input"]
        cached_price = PRICING["gpt-4o"]["cached_input"]
        hypothetical_cost = (total_cached * input_price) / 1000
        actual_cached_cost = (total_cached * cached_price) / 1000
        estimated_cost_saved_usd = round(hypothetical_cost - actual_cached_cost, 6)

        by_action = {
            r["action"]: {
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
                "cached_tokens": int(r["cached_tokens"]),
                "cost_usd": float(r["cost_usd"]),
            }
            for r in db.rows(
                f"""
                SELECT action,
                    COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                    COALESCE(SUM(cost_usd), 0)      AS cost_usd
                FROM usage_ledger
                {where}
                GROUP BY action
                """,
                params,
            )
        }

        by_model = {
            r["model"]: {
                "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]),
                "cached_tokens": int(r["cached_tokens"]),
                "cost_usd": float(r["cost_usd"]),
            }
            for r in db.rows(
                f"""
                SELECT model,
                    COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                    COALESCE(SUM(cost_usd), 0)      AS cost_usd
                FROM usage_ledger
                {where}
                GROUP BY model
                """,
                params,
            )
        }

        return {
            "total_input_tokens": int(totals["total_input_tokens"]),
            "total_output_tokens": int(totals["total_output_tokens"]),
            "total_cached_tokens": total_cached,
            "total_tokens": int(totals["total_tokens"]),
            "total_cost_usd": round(float(totals["total_cost_usd"]), 6),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": cache_hit_rate,
            "tokens_saved_by_cache": total_cached,
            "estimated_cost_saved_usd": estimated_cost_saved_usd,
            "by_action": by_action,
            "by_model": by_model,
            "events": int(totals["events"]),
        }


def _now() -> str:
    """Return current UTC timestamp in SQLite-compatible format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
