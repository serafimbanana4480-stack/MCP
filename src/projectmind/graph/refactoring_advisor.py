from .smells import detect_smells
from .store import GraphStore


def suggestions(store: GraphStore) -> list[dict[str, object]]:
    return [
        {
            "target": s.get("node", "graph"),
            "smell": s["type"],
            "rationale": "Reduzir acoplamento e aumentar coesão",
            "expected_impact": "blast radius menor",
        }
        for s in detect_smells(store)
    ]
