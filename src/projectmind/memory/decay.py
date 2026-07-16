from datetime import UTC, datetime

from ..core.db import Database


def apply_decay(db: Database, half_life_days: float = 90) -> int:
    now = datetime.now(UTC)
    rows = db.rows(
        "SELECT id,confidence,last_verified_at FROM memories WHERE status='active' AND last_verified_at IS NOT NULL"
    )
    updated = 0
    for row in rows:
        try:
            days = max(0, (now - datetime.fromisoformat(row["last_verified_at"])).days)
        except ValueError:
            continue
        confidence = row["confidence"] * (0.5 ** (days / half_life_days))
        db.execute(
            "UPDATE memories SET confidence=?,updated_at=datetime('now') WHERE id=?",
            (confidence, row["id"]),
        )
        updated += 1
    return updated
