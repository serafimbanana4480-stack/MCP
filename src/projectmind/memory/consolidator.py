from ..core.db import Database


def consolidate(db: Database) -> dict[str, object]:
    rows = db.rows(
        "SELECT type,COUNT(*) AS count FROM memories WHERE status='active' GROUP BY type"
    )
    return {
        "consolidated": False,
        "message": "Memórias já estruturadas; consolidação LLM local pode ser adicionada via integração explícita.",
        "by_type": rows,
    }
