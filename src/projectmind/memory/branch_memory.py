from ..core.db import Database


def set_branch(db: Database, name: str, memories: list[str] | None = None) -> dict:
    db.execute(
        "INSERT INTO branches(name,metadata) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET metadata=excluded.metadata",
        (name, __import__("json").dumps({"memories": memories or []})),
    )
    return db.one("SELECT * FROM branches WHERE name=?", (name,)) or {}
