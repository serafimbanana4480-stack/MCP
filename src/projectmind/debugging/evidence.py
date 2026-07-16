def collect(symptom: str, stacktrace: str = "", recent_changes: list[str] | None = None) -> dict:
    from .stacktrace_parser import parse

    return {
        "symptom": symptom,
        "stacktrace": stacktrace,
        "frames": parse(stacktrace),
        "recent_changes": recent_changes or [],
        "evidence_count": len(parse(stacktrace)) + len(recent_changes or []),
    }
