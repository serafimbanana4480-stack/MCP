def precision_at_k(relevant: set[str], returned: list[str], k: int = 5) -> float:
    values = returned[:k]
    return sum(x in relevant for x in values) / max(1, len(values))
