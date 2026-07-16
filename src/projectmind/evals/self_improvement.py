def suggest(telemetry: list[dict]) -> dict:
    counts = {}
    for item in telemetry:
        counts[item.get("action", "unknown")] = counts.get(item.get("action", "unknown"), 0) + 1
    return {"observed_actions": counts, "suggestions": ["avaliar pesos após feedback suficiente"]}
