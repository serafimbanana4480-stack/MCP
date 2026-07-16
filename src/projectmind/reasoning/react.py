def step(thought: str, previous_actions: list[dict] | None = None, loop_count: int = 0) -> dict:
    if loop_count > 10:
        return {
            "next_action_type": "finish",
            "rationale": "limite do loop atingido",
            "loop_count": loop_count,
        }
    return {
        "next_action_type": "tool",
        "suggested_tool": "get_relevant_context",
        "suggested_args": {"task": thought, "token_budget": 1200, "mode": "surgical"},
        "rationale": "Obter evidência antes de agir",
        "loop_count": loop_count + 1,
    }
