import json

from .store import MemoryStore


def export_memory(store: MemoryStore) -> str:
    return json.dumps(store.db.rows("SELECT * FROM memories"), ensure_ascii=False, default=str)


def import_memory(store: MemoryStore, payload: str) -> dict:
    items = json.loads(payload)
    count = 0
    for item in items:
        store.record(
            item["type"],
            item["title"],
            item["body"],
            item["confidence"],
            item["provenance"],
            item.get("branch"),
        )
        count += 1
    return {"imported": count}
