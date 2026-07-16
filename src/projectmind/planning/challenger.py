def challenge(plan: dict, perspectives: list[str] | None = None) -> dict:
    perspectives = perspectives or ["retrocompat", "seguranca", "testes", "performance", "UX/DX"]
    challenges = []
    if not plan.get("test_strategy"):
        challenges.append({"perspective": "testes", "finding": "Não há estratégia de testes."})
    if not plan.get("mitigations"):
        challenges.append({"perspective": "seguranca", "finding": "Não há mitigações explícitas."})
    return {"challenges": challenges, "must_fix": bool(challenges), "perspectives": perspectives}
