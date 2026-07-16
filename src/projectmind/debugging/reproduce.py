def reproduce(symptom: str, inputs: dict | None = None) -> dict:
    return {
        "symptom": symptom,
        "inputs": inputs or {},
        "reproduction": "Criar teste mínimo com os inputs fornecidos",
        "status": "proposal",
    }
