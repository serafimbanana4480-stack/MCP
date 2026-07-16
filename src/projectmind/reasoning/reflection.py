def reflect(output: str, perspectives: list[str] | None = None) -> dict:
    perspectives = perspectives or ["architect", "security", "test_engineer", "performance"]
    critiques = [
        {
            "perspective": p,
            "critique": "Verificar evidência, reversibilidade e cobertura de testes.",
            "severity": "medium",
        }
        for p in perspectives
    ]
    return {
        "critiques": critiques,
        "overall_score": 70,
        "must_fix_before_proceed": False,
        "output_ref": output,
    }


def critique_edit(edit: dict, perspectives: list[str] | None = None) -> dict:
    findings = []
    if not edit.get("diff") and edit.get("old_content") == edit.get("new_content"):
        findings.append("Alteração vazia")
    return {
        "verdict": "reject" if findings else "approve",
        "findings": findings,
        "suggested_tests": ["executar testes relevantes"],
        "perspectives": perspectives or ["security", "test_engineer"],
        "overall_score": 0 if findings else 85,
    }
