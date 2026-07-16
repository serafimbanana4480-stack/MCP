import hashlib
import json

from ..core.db import Database


def get_or_none(db: Database, task: str):
    key = hashlib.sha256(task.strip().lower().encode()).hexdigest()
    row = db.one("SELECT result FROM task_cache WHERE task_hash=?", (key,))
    return json.loads(row["result"]) if row else None


def put(db: Database, task: str, result: dict):
    key = hashlib.sha256(task.strip().lower().encode()).hexdigest()
    db.execute(
        "INSERT OR REPLACE INTO task_cache(task_hash,task,result,created_at) VALUES(?,?,?,datetime('now'))",
        (key, task, json.dumps(result, default=str)),
    )
