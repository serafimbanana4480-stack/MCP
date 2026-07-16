def generate(target: str, symptom: str) -> dict:
    return {
        "target": target,
        "test_name": "test_regression_case",
        "scenario": symptom,
        "status": "proposal",
    }
