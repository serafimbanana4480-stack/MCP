from __future__ import annotations

from datetime import UTC, datetime

from ..core.db import Database


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db

    def record(
        self,
        type: str,
        title: str,
        body: str,
        confidence: float = 0.8,
        provenance: str = "user_decision",
        branch: str | None = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT INTO memories(type,title,body,confidence,provenance,branch,last_verified_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(type,title,branch) DO UPDATE SET body=excluded.body,confidence=excluded.confidence,provenance=excluded.provenance,updated_at=excluded.updated_at,last_verified_at=excluded.last_verified_at,status='active'",
            (type, title, body, confidence, provenance, branch, now, now, now),
        )
        return (
            self.db.one(
                "SELECT * FROM memories WHERE type=? AND title=? AND (branch IS ? OR branch=?)",
                (type, title, branch, branch),
            )
            or {}
        )

    def search(
        self,
        query: str,
        type: str | None = None,
        min_confidence: float = 0,
        provenance: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        clauses = ["status='active'", "confidence>=?"]
        params: list[object] = [min_confidence]
        if type:
            clauses.append("type=?")
            params.append(type)
        if provenance:
            clauses.append("provenance=?")
            params.append(provenance)
        clauses.append("(title LIKE ? OR body LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
        params.append(limit)
        return self.db.rows(
            f"SELECT * FROM memories WHERE {' AND '.join(clauses)} ORDER BY confidence DESC,updated_at DESC LIMIT ?",
            params,
        )

    def feedback(self, context_ref: str, signal: str, note: str = "") -> dict:
        self.db.execute(
            "INSERT INTO memory_feedback(context_ref,signal,note,created_at) VALUES(?,?,?,datetime('now'))",
            (context_ref, signal, note),
        )
        return {"recorded": True, "context_ref": context_ref, "signal": signal}
