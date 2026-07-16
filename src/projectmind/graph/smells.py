from .store import GraphStore


def detect_smells(store: GraphStore) -> list[dict[str, object]]:
    graph = store.graph()
    smells = [
        {"type": "dependency_cycle", "nodes": list(c)}
        for c in __import__("networkx").simple_cycles(graph)
        if len(c) > 1
    ]
    for n, d in graph.nodes(data=True):
        degree = graph.degree(n)
        if d.get("type") == "class" and degree > 20:
            smells.append({"type": "god_class", "node": n, "degree": degree})
        if degree > 30:
            smells.append({"type": "tight_coupling", "node": n, "degree": degree})
    return smells
