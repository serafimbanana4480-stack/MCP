from .store import GraphStore


def critical_files(store: GraphStore, limit: int = 10) -> list[dict[str, object]]:
    graph = store.graph()
    scores = __import__("networkx").pagerank(graph) if graph else {}
    return sorted(
        (
            {"node": n, "score": score, **graph.nodes[n]}
            for n, score in scores.items()
            if graph.nodes[n].get("type") == "File"
        ),
        key=lambda x: x["score"],
        reverse=True,
    )[:limit]
