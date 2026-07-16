REQUIRED = (
    "objective",
    "assumptions",
    "dependencies",
    "risks",
    "mitigations",
    "test_strategy",
    "completion_criteria",
)


def validate(plan: dict) -> dict:
    missing = [key for key in REQUIRED if not plan.get(key)]
    return {
        "valid": not missing,
        "missing": missing,
        "status": "validated" if not missing else "blocked",
    }
