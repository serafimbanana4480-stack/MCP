from projectmind.core.db import Database
from projectmind.memory.store import MemoryStore


def test_memory_persists_and_searches(tmp_path):
    store = MemoryStore(Database(tmp_path / "db.sqlite"))
    store.record("decision", "database", "Use SQLite", 0.9, "user_decision")
    assert store.search("SQLite")[0]["title"] == "database"
