def force(question: str, template: str = "premises") -> dict:
    return {
        "question": question,
        "template": template,
        "premises": [],
        "alternatives": [],
        "decision": "",
        "rationale": "Preencher com evidências do projeto.",
    }
