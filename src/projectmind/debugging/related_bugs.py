def related(memories: list[dict], symptom: str) -> list[dict]:
    terms = set(symptom.lower().split())
    return [m for m in memories if terms & set(m.get("body", "").lower().split())]
