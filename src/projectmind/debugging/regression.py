def analyze(before: str, after: str, tests: list[str] | None = None) -> dict:
    return {
        "changed": before != after,
        "regression_risk": "low" if tests else "medium",
        "tests": tests or [],
    }
