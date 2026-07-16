def root_cause(evidence: dict) -> dict:
    frames = evidence.get("frames", [])
    cause = (
        f"Falha em {frames[0]['file']}:{frames[0]['line']}"
        if frames
        else evidence.get("symptom", "Causa ainda não localizada")
    )
    return {
        "likely_cause": cause,
        "evidence_chain": frames or [evidence.get("symptom", "")],
        "confidence": 0.65 if frames else 0.25,
    }
