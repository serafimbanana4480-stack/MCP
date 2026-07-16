from .store import GraphStore


def impact(store: GraphStore, target: str, depth: int = 2) -> dict[str, object]:
    graph = store.graph()
    matches = [
        n for n, d in graph.nodes(data=True) if d.get("label") == target or n.endswith(":" + target)
    ]
    result = set()
    for node in matches:
        result.update(
            __import__("networkx").single_source_shortest_path_length(
                graph.to_undirected(), node, cutoff=depth
            )
        )
    return {
        "target": target,
        "depth": depth,
        "affected_nodes": [dict(id=n, **graph.nodes[n]) for n in sorted(result)],
        "count": len(result),
    }
