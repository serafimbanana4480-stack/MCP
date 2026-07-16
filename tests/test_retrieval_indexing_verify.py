from __future__ import annotations

from pathlib import Path

import pytest

from projectmind.application import ProjectMind
from projectmind.core.config import Config
from projectmind.git.diff_parser import unified
from projectmind.indexing.reindex_on_pull import should_reindex
from projectmind.indexing.symbol_extractor import extract_symbols
from projectmind.retrieval.hybrid_retriever import retrieve
from projectmind.retrieval.ranking import lexical_score, rank_file
from projectmind.retrieval.summarizer import summarize
from projectmind.retrieval.task_cache import get_or_none, put
from projectmind.retrieval.token_budget import trim_to_budget


PY_SRC = '''
def helper(x):
    """A helper."""
    if x:
        return x
    return 0

async def fetch(url):
    return url

class Service:
    def method(self):
        return 1
'''


JS_SRC = '''
export function login(user) {
  return user;
}

class Auth {
  constructor() {}
}
'''


@pytest.fixture
def project(tmp_path: Path) -> ProjectMind:
    (tmp_path / "svc.py").write_text(PY_SRC, encoding="utf-8")
    (tmp_path / "auth.js").write_text(JS_SRC, encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "util.py").write_text("def util():\n    pass\n", encoding="utf-8")
    return ProjectMind(tmp_path)


def test_project_scan_indexes_files(project: ProjectMind):
    res = project.tool_project_scan()
    assert res["indexed"] > 0
    assert res["total"] == res["indexed"] + res["skipped"]


def test_find_symbol(project: ProjectMind):
    project.tool_project_scan()
    res = project.tool_find_symbol("Service")
    names = {s["name"] for s in res["symbols"]}
    assert "Service" in names


def test_get_file_overview(project: ProjectMind):
    project.tool_project_scan()
    res = project.tool_get_file_overview("svc.py")
    assert res["file"]["indexed"] is True or res.get("file")
    assert any(s["name"] == "helper" for s in res.get("symbols", []))


def test_project_summary(project: ProjectMind):
    project.tool_project_scan()
    summary = project.tool_project_summary()
    assert summary["files"] > 0
    assert summary["symbols"] > 0


def test_get_relevant_context_small_budget(project: ProjectMind):
    project.tool_project_scan()
    res = project.tool_get_relevant_context("Service", token_budget=50)
    assert "files" in res
    total_chars = sum(len(str(f.get("content", ""))) for f in res["files"])
    assert total_chars <= 50 * 4 + 200


def test_symbol_extractor_python_ast():
    syms = extract_symbols(Path("x.py"), PY_SRC)
    kinds = {s["name"]: s["kind"] for s in syms}
    assert kinds.get("helper") == "function"
    assert kinds.get("fetch") == "function"
    assert kinds.get("Service") == "class"
    assert any(s["name"] == "method" for s in syms)
    helper = next(s for s in syms if s["name"] == "helper")
    assert helper["start_line"] == 2 or helper["start_line"] >= 2


def test_symbol_extractor_js_regex_fallback():
    syms = extract_symbols(Path("x.js"), JS_SRC)
    names = {s["name"] for s in syms}
    assert "login" in names
    assert "Auth" in names


def test_config_safe_path_inside_root(tmp_path: Path):
    cfg = Config.load(tmp_path)
    p = cfg.safe_path("svc.py")
    assert tmp_path in p.parents or p == tmp_path / "svc.py"


def test_config_safe_path_outside_root_rejected(tmp_path: Path):
    cfg = Config.load(tmp_path)
    with pytest.raises(ValueError):
        cfg.safe_path("../../etc/passwd")


def test_config_safe_path_absolute_outside_root(tmp_path: Path):
    cfg = Config.load(tmp_path)
    with pytest.raises(ValueError):
        cfg.safe_path("/etc/passwd")


def test_lexical_score():
    assert lexical_score("auth login", "src/auth.py login") > 0
    assert lexical_score("zzzqqq", "src/auth.py login") == 0.0
    assert lexical_score("ab", "anything") == 0.0


def test_rank_file_breakdown_and_weighting():
    weights = {"graph_relevance": 0.35, "semantic_similarity": 0.25,
               "lexical_match": 0.20, "recency_git": 0.10, "architectural_importance": 0.10}
    row = {"path": "src/auth.py", "content": "auth login service", "id": 1}
    ranked = rank_file("auth login", row, importance=0.5, recency=0.2, graph=0.8, weights=weights)
    assert set(ranked["scoring_breakdown"]) == set(weights)
    assert ranked["relevance"] == pytest.approx(
        0.35 * 0.8 + 0.25 * 1.0 + 0.20 * 1.0 + 0.10 * 0.2 + 0.10 * 0.5
    )


def test_retrieve_returns_ranked_and_cached(project: ProjectMind):
    project.tool_project_scan()
    r1 = retrieve(project.db, "Service", 200, project.config.weights, "exploratory")
    assert "files" in r1
    assert r1["cache_hit"] is False
    r2 = retrieve(project.db, "Service", 200, project.config.weights, "exploratory")
    assert r2["cache_hit"] is True


def test_task_cache_put_get(tmp_path: Path):
    db = Config.load(tmp_path).db if False else None
    from projectmind.core.db import Database

    db = Database(tmp_path / ".pm" / "t.db")
    payload = {"files": [{"id": 1}]}
    assert get_or_none(db, "lookup") is None
    put(db, "lookup", payload)
    assert get_or_none(db, "LOOKUP")["files"] == [{"id": 1}]


def test_token_budget_trim(tmp_path: Path):
    items = [
        {"id": i, "content": "x" * 400, "relevance": i}
        for i in range(5)
    ]
    out = trim_to_budget(items, token_budget=300)
    assert out
    assert all(len(str(o["content"])) <= 300 * 4 for o in out)
    assert [o["id"] for o in out] == sorted([o["id"] for o in out], reverse=True)


def test_summarizer():
    content = "\n".join([f"line {i}" for i in range(50)])
    s = summarize(content, max_chars=100)
    assert len(s) <= 100
    assert "line 0" in s


def test_diff_parser_unified():
    diff = unified("a\nb\n", "a\nc\n", "f.py")
    assert diff.startswith("--- f.py")
    assert "+++ f.py" in diff
    assert "+c" in diff


def test_should_reindex():
    assert should_reindex("abc", "def") is True
    assert should_reindex("abc", "abc") is False
    assert should_reindex(None, "def") is False
    assert should_reindex("abc", None) is False
