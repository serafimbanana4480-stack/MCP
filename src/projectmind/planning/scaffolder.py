def boilerplate(objective: str, conventions: list[str] | None = None) -> dict:
    return {
        "objective": objective,
        "conventions": conventions or [],
        "edits": [],
        "requires_proposal": True,
    }
