def check(plan: dict, evidence: list | None = None) -> dict:
    evidence = evidence or []
    criteria = plan.get("completion_criteria", [])
    unmet = [c for c in criteria if not any(c.lower() in str(e).lower() for e in evidence)]
    return {"complete": not unmet and bool(criteria), "unmet_criteria": unmet, "evidence": evidence}
