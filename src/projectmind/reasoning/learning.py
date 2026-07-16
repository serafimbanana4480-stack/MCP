def make_learning(task_ref: str, outcome: str, lessons: list[str], **kwargs) -> dict:
    return {"task_ref": task_ref, "outcome": outcome, "lessons": lessons, **kwargs}
