from projectmind.core.db import Database
from projectmind.graph.store import GraphStore


def test_graph_export_empty_is_valid(tmp_path):
    output = GraphStore(Database(tmp_path / "db.sqlite")).export("mermaid")
    assert output.startswith("flowchart LR")
