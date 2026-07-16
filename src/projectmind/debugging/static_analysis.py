from ..core.security import run_sandbox


def analyze(config, command: str = "ruff check .") -> dict:
    try:
        return run_sandbox(command, config)
    except Exception as exc:
        return {"status": "blocked", "error": str(exc)}
