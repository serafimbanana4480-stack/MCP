def score(ref: str, evidence: list | None = None) -> dict:
    evidence = evidence or []
    value = min(100, 30 + len(evidence) * 15)
    return {
        "ref": ref,
        "score": value,
        "justification": f"{len(evidence)} evidência(s) associada(s)",
        "uncertainty_sources": [] if evidence else ["evidência insuficiente"],
    }
