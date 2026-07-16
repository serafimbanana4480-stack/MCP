def explore(proposal: str, num_branches: int = 3, axes: list[str] | None = None) -> dict:
    axes = axes or ["segurança", "custo", "testabilidade"]
    branches = [
        {
            "branch_id": str(i + 1),
            "proposal": f"{proposal} (variante {i + 1})",
            "score": max(0, 1 - i * 0.15),
            "evaluation_axes": axes,
            "pros": [],
            "cons": [],
        }
        for i in range(num_branches)
    ]
    return {
        "branches": branches,
        "selected": branches[0]["branch_id"] if branches else None,
        "rationale": "Ramo com maior score inicial; submeter a challenge_plan.",
    }
