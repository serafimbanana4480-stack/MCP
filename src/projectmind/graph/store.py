from __future__ import annotations

import networkx as nx

from ..core.db import Database


class GraphStore:
    def __init__(self, db: Database):
        self.db = db

    def graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        for row in self.db.rows("SELECT id,path FROM files"):
            graph.add_node(f"file:{row['id']}", type="File", label=row["path"])
        for row in self.db.rows("SELECT id,file_id,name,kind FROM symbols"):
            graph.add_node(f"symbol:{row['id']}", type=row["kind"], label=row["name"])
            graph.add_edge(f"file:{row['file_id']}", f"symbol:{row['id']}", relation="CONTAINS")
        for row in self.db.rows(
            "SELECT source_type,source_id,target_type,target_id,relation,confidence FROM edges"
        ):
            graph.add_edge(
                f"{row['source_type']}:{row['source_id']}",
                f"{row['target_type']}:{row['target_id']}",
                relation=row["relation"],
                confidence=row["confidence"],
            )
        return graph

    def export(self, fmt: str = "json") -> str:
        graph = self.graph()
        if fmt == "mermaid":
            return "flowchart LR\n" + "\n".join(
                f"  {a.replace(':', '_')} -->|{d.get('relation', 'RELATES')}| {b.replace(':', '_')}"
                for a, b, d in graph.edges(data=True)
            )
        if fmt == "dot":
            return "\n".join(f'"{a}" -> "{b}";' for a, b in graph.edges())
        if fmt == "plantuml":
            return "@startuml\n" + "\n".join(f"{a} --> {b}" for a, b in graph.edges()) + "\n@enduml"
        return __import__("json").dumps(
            {
                "nodes": [{"id": n, **d} for n, d in graph.nodes(data=True)],
                "edges": [{"source": a, "target": b, **d} for a, b, d in graph.edges(data=True)],
            },
            default=str,
        )
