def checkpoint(task: dict, event: str, state: dict | None = None) -> dict:
    task.setdefault("checkpoints", []).append({"event": event, "state": state or {}})
    task["status"] = "active"
    return task
