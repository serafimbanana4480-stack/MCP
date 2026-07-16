def compare(alternatives: list[dict]) -> dict:
    if not alternatives:
        return {
            "selected": None,
            "ranking": [],
            "status": "blocked",
            "reason": "no alternatives provided",
        }
    for item in alternatives:
        item.setdefault("pros", [])
        item.setdefault("cons", [])
        item.setdefault("cost", "unknown")
        item.setdefault("migration", "unknown")
        item["score"] = len(item["pros"]) - len(item["cons"])
    selected = max(alternatives, key=lambda x: x.get("score", 0), default=None)
    return {
        "alternatives": alternatives,
        "selected": selected.get("name") if selected else None,
        "rationale": "Maior saldo de prós/contras declarados.",
    }
