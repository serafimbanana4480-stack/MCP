from .store import GraphStore


def neighbors(store: GraphStore, target: str, depth: int = 1) -> list[str]:
    graph = store.graph()
    matches = [
        n
        for n, d in graph.nodes(data=True)
        if d.get("label") == target or n == target or n.endswith(":" + target)
    ]
    found = set()
    for node in matches:
        found.update(
            __import__("networkx").single_source_shortest_path_length(
                graph.to_undirected(), node, cutoff=depth
            )
        )
    return sorted(found)
