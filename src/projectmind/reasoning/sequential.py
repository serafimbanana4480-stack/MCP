def next_step(
    session: dict, thought: str, success_criteria: list[str], confidence: float = 0.6
) -> dict:
    index = len(session.get("steps", [])) + 1
    step = {
        "step_index": index,
        "thought": thought,
        "success_criteria": success_criteria,
        "status": "passed",
        "confidence": confidence,
    }
    session.setdefault("steps", []).append(step)
    session["current_step"] = index
    return step
