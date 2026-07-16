def challenge(proposal: str, focus: str = "risco") -> dict:
    return {
        "proposal": proposal,
        "focus": focus,
        "counter_arguments": [
            f"O que falha se {focus} for subestimado?",
            "Qual é a alternativa reversível?",
        ],
        "weakest_point": "Assunções não verificadas",
        "resilient_if": "Adicionar teste e rollback explícito.",
    }
