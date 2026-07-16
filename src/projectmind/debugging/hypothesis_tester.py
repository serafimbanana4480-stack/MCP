def prioritize(hypotheses: list[dict]) -> list[dict]:
    return sorted(
        hypotheses,
        key=lambda h: h.get("probability", 0.5) / max(h.get("test_cost", 1), 0.01),
        reverse=True,
    )
