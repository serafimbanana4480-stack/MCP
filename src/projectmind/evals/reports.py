def report(results: list[dict]) -> dict:
    return {
        "scenarios": len(results),
        "passed": sum(bool(x.get("passed")) for x in results),
        "results": results,
    }
