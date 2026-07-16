from __future__ import annotations

import json
from pathlib import Path

from projectmind.application import ProjectMind
from projectmind.core.db import Database
from projectmind.graph.centrality import critical_files
from projectmind.graph.impact import impact
from projectmind.graph.refactoring_advisor import suggestions
from projectmind.graph.smells import detect_smells
from projectmind.graph.store import GraphStore
from projectmind.graph.whatif import simulate
from projectmind.memory.branch_memory import set_branch
from projectmind.memory.consolidator import consolidate
from projectmind.memory.decay import apply_decay
from projectmind.memory.io import export_memory, import_memory
from projectmind.memory.provenance import validate as validate_provenance
from projectmind.memory.store import MemoryStore

EXAMPLE_SOURCE = '''
"""Example module for ProjectMind indexing tests."""

import os
import json


class Service:
    """A simple service."""

    def __init__(self, name):
        self.name = name

    def run(self):
        return self.name

    def helper(self):
        return 42


def top_level_function(x):
    return x * 2


class BigClass:
    """Intentionally huge to allow god_class checks if needed."""
    pass
'''


def _write_example_project(root: Path) -> None:
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "app" / "service.py").write_text(EXAMPLE_SOURCE, encoding="utf-8")
    (root / "app" / "main.py").write_text(
        "from app.service import Service\n\n\ndef main():\n    s = Service('x')\n    return s.run()\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_service.py").write_text(
        "def test_run():\n    assert True\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Setup / scanning
# ---------------------------------------------------------------------------


def test_instantiate_components_directly(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    gs = GraphStore(db)
    ms = MemoryStore(db)
    pm = ProjectMind(tmp_path)
    assert gs.db is db
    assert ms.db is db
    assert pm.graph is gs  # type independent instance but same db-backed
    assert pm.memory is ms


def test_project_scan_indexes_example_project(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    result = pm.tool_project_scan()
    assert result["indexed"] >= 3
    assert result["total"] >= 3
    files = pm.db.rows("SELECT path FROM files ORDER BY path")
    paths = [f["path"] for f in files]
    assert "app/main.py" in paths
    assert "app/service.py" in paths
    assert "tests/test_service.py" in paths
    symbols = pm.db.rows("SELECT name, kind FROM symbols")
    names = {s["name"] for s in symbols}
    assert "Service" in names
    assert "top_level_function" in names


# ---------------------------------------------------------------------------
# Graph tests
# ---------------------------------------------------------------------------


def test_graph_export_mermaid_has_real_edges(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    out = pm.graph.export("mermaid")
    assert out.startswith("flowchart LR")
    assert "file_" in out or "symbol_" in out


def test_graph_export_dot(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    out = pm.graph.export("dot")
    assert "-->" in out or '->' in out


def test_graph_export_json_contains_nodes_and_edges(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    out = json.loads(pm.graph.export("json"))
    assert "nodes" in out and "edges" in out
    assert len(out["nodes"]) > 0
    # file -> symbol CONTAINS edges exist
    assert any(e["relation"] == "CONTAINS" for e in out["edges"])


def test_tool_export_diagram_all_formats(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    for fmt in ("mermaid", "dot", "json"):
        res = pm.tool_export_diagram(format=fmt)
        assert res["format"] == fmt
        assert res["diagram"]


def test_critical_files_returns_only_files(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.tool_critical_files(limit=10)
    files = res["files"]
    assert isinstance(files, list)
    for f in files:
        assert f["type"] == "File"
        assert "score" in f


def test_critical_files_via_direct_call(tmp_path):
    _write_example_project(tmp_path)
    db = Database(tmp_path / "db.sqlite")
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    result = critical_files(pm.graph, 5)
    assert all(r["type"] == "File" for r in result)


def test_detect_smells_runs(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.tool_detect_smells()
    assert "smells" in res
    smells = detect_smells(pm.graph)
    assert isinstance(smells, list)


def test_suggest_refactoring_mirrors_smells(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.tool_suggest_refactoring()
    sugg = res["suggestions"]
    assert isinstance(sugg, list)
    for s in sugg:
        assert "target" in s and "smell" in s
    direct = suggestions(pm.graph)
    assert len(direct) == len(sugg)


def test_impact_analysis_blast_radius(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.tool_impact_analysis(target="app/service.py", depth=2)
    assert res["target"] == "app/service.py"
    assert res["depth"] == 2
    assert res["count"] > 0
    # target node itself is part of affected set
    ids = [n["id"] for n in res["affected_nodes"]]
    assert "file:1" in ids or "file:2" in ids


def test_trace_request_flow(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.tool_trace_request_flow(entrypoint="app/main.py", max_depth=3)
    assert "entrypoint" in res and "flow" in res
    assert isinstance(res["flow"], list)


def test_simulate_change(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.tool_simulate_change(target="Service", change_type="modify", depth=2)
    assert res["change_type"] == "modify"
    assert "warning" in res
    assert res["count"] > 0
    # direct call equivalent
    direct = simulate(pm.graph, "Service", "delete", 2)
    assert direct["change_type"] == "delete"


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------


def test_memory_record_and_search(tmp_path):
    store = MemoryStore(Database(tmp_path / "db.sqlite"))
    store.record("decision", "DB choice", "Use SQLite", 0.9, "user_decision")
    hits = store.search("SQLite")
    assert hits and hits[0]["title"] == "DB choice"
    assert hits[0]["confidence"] >= 0.9


def test_memory_search_filters_by_type_and_confidence(tmp_path):
    store = MemoryStore(Database(tmp_path / "db.sqlite"))
    store.record("decision", "A", "alpha content", 0.9, "user_decision")
    store.record("episodic", "B", "beta content", 0.2, "test_result")
    by_type = store.search("content", type="decision")
    assert all(r["type"] == "decision" for r in by_type)
    high = store.search("content", min_confidence=0.5)
    assert all(r["confidence"] >= 0.5 for r in high)


def test_tool_memory_search(tmp_path):
    pm = ProjectMind(tmp_path)
    pm.memory.record("semantic", "Cache", "redis cache layer", 0.8, "llm_inference")
    res = pm.tool_memory_search(query="redis", limit=5)
    assert res["memories"][0]["title"] == "Cache"


def test_record_decision_and_attempt(tmp_path):
    pm = ProjectMind(tmp_path)
    d = pm.tool_record_decision(title="T1", decision="do X", rationale="because")
    assert d["type"] == "decision"
    a = pm.tool_record_attempt(title="T2", body="tried Y")
    assert a["type"] == "episodic"


def test_memory_feedback(tmp_path):
    pm = ProjectMind(tmp_path)
    res = pm.tool_memory_feedback(context_ref="mem:1", signal="up", note="good")
    assert res["recorded"] is True
    rows = pm.db.rows("SELECT * FROM memory_feedback")
    assert rows[-1]["signal"] == "up"


def test_memory_export_import_roundtrip(tmp_path):
    pm = ProjectMind(tmp_path)
    pm.memory.record("decision", "Exp", "export me", 0.9, "user_decision")
    data = pm.tool_export_memory()["data"]
    parsed = json.loads(data)
    assert any(m["title"] == "Exp" for m in parsed)
    # import into a fresh store
    other = ProjectMind(tmp_path / "other")
    out = other.tool_import_memory(data)
    assert out["imported"] >= 1
    assert other.memory.search("export me")


def test_set_branch_memory(tmp_path):
    pm = ProjectMind(tmp_path)
    res = pm.tool_set_branch_memory(branch="feature/x", memories=["m1", "m2"])
    assert res["name"] == "feature/x"
    row = pm.db.one("SELECT metadata FROM branches WHERE name=?", ("feature/x",))
    assert json.loads(row["metadata"])["memories"] == ["m1", "m2"]


def test_find_similar_past_solutions(tmp_path):
    pm = ProjectMind(tmp_path)
    pm.memory.record("semantic", "OOM fix", "reduced buffer size", 0.7, "test_result")
    res = pm.tool_find_similar_past_solutions(task="buffer")
    assert res["matches"]


def test_consolidate_memory(tmp_path):
    pm = ProjectMind(tmp_path)
    pm.memory.record("decision", "C", "c", 0.9, "user_decision")
    res = pm.tool_consolidate_memory()
    assert "by_type" in res
    direct = consolidate(pm.db)
    assert direct["consolidated"] is False


# ---------------------------------------------------------------------------
# Decay and provenance
# ---------------------------------------------------------------------------


def test_apply_decay_reduces_old_confidence(tmp_path):
    store = MemoryStore(Database(tmp_path / "db.sqlite"))
    store.record(
        "decision", "Old", "stale memory", 1.0, "user_decision"
    )
    # Force last_verified_at far in the past via direct update
    store.db.execute(
        "UPDATE memories SET last_verified_at='2000-01-01T00:00:00+00:00' WHERE title='Old'"
    )
    updated = apply_decay(store.db, half_life_days=90)
    assert updated >= 1
    row = store.db.one("SELECT confidence FROM memories WHERE title='Old'")
    assert row["confidence"] < 1.0


def test_apply_decay_returns_zero_when_none_verified(tmp_path):
    store = MemoryStore(Database(tmp_path / "db.sqlite"))
    # record sets last_verified_at; clear it to simulate unverifiable
    store.record("decision", "NoDate", "x", 0.9, "user_decision")
    store.db.execute("UPDATE memories SET last_verified_at=NULL WHERE title='NoDate'")
    assert apply_decay(store.db) == 0


def test_provenance_validate_accepts_known_values(tmp_path):
    assert validate_provenance("user_decision") == "user_decision"
    assert validate_provenance("code_fact") == "code_fact"


def test_provenance_validate_rejects_unknown(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        validate_provenance("not_a_provenance")


def test_call_tool_dispatch(tmp_path):
    _write_example_project(tmp_path)
    pm = ProjectMind(tmp_path)
    pm.tool_project_scan()
    res = pm.call("detect_smells", {})
    assert res["status"] != "blocked"
    assert "smells" in res
