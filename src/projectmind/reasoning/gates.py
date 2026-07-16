from ..core.exceptions import GateBlocked


def require(condition: bool, reason: str, suggested_tool: str = "") -> None:
    if not condition:
        raise GateBlocked(
            f"{reason}. suggested_tool={suggested_tool}" if suggested_tool else reason
        )


def validate_step(step: dict) -> dict:
    if not step.get("thought") or not step.get("success_criteria"):
        return {
            "valid": False,
            "status": "blocked",
            "blocked_reason": "thought e success_criteria são obrigatórios",
        }
    return {"valid": True, "status": "passed", "blocked_reason": None}
