def assess(plan_id: str, risks: list[dict]) -> dict:
    result = []
    for r in risks:
        score = float(r.get("probability", 0)) * float(r.get("impact", 0))
        tier = (
            "critical"
            if score >= 0.75
            else "high"
            if score >= 0.5
            else "medium"
            if score >= 0.25
            else "low"
        )
        result.append({**r, "score": score, "tier": tier})
    blocked = any(x["tier"] in {"high", "critical"} and not x.get("mitigation") for x in result)
    return {"plan_id": plan_id, "risks": result, "blocked": blocked}
