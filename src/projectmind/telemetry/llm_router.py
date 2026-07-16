def route(task: str) -> dict:
    return {
        "task": task,
        "provider": "local",
        "reason": "ProjectMind não envia conteúdo externo por defeito.",
    }
