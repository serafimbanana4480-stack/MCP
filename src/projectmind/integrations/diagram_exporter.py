from ..graph.store import GraphStore


def export(store: GraphStore, fmt: str = "mermaid") -> str:
    return store.export(fmt)
