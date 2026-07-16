"""Usage dashboard & real-metrics verification tests for ProjectMind.

These tests are designed for environments where pytest cannot be executed
(shell disabled). They are written to be statically inspectable and will
run under pytest where available.

All metrics are validated against the REAL sqlite `usage_ledger` (no mocks).
Each test instantiates `ProjectMind(tmp_path)` and indexes real .py files.

Coverage:
  1. project_scan populates a real usage_ledger record (action=project_scan, input_tokens>0)
  2. get_relevant_context records usage + task_cache hit on 2nd identical call
  3. record_decision / memory_search record usage
  4. propose_edit records usage
  5. tool_usage_dashboard_data returns real aggregated data
  6. UsageStats.summary aggregates totals
  7. estimate_tokens deterministic real behaviour
"""

from __future__ import annotations

from pathlib import Path

import pytest

from projectmind.application import ProjectMind
from projectmind.telemetry.usage import UsageStats, estimate_tokens


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_app(tmp_path: Path) -> ProjectMind:
    """Build a ProjectMind rooted at tmp_path (isolated sqlite db)."""
    return ProjectMind(tmp_path)


def write_py(tmp_path: Path, name: str, content: str) -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")


def ledger_rows(app: ProjectMind, action: str | None = None) -> list[dict]:
    if action is None:
        return app.db.rows("SELECT * FROM usage_ledger")
    return app.db.rows("SELECT * FROM usage_ledger WHERE action=?", (action,))


# --------------------------------------------------------------------------- #
# 1. project_scan populates real usage
# --------------------------------------------------------------------------- #
def test_project_scan_records_usage(tmp_path):
    app = make_app(tmp_path)
    write_py(tmp_path, "app.py", "def login():\n    return True\n")
    app.tool_project_scan()

    rows = app.db.rows("SELECT * FROM usage_ledger")
    assert any(
        r["action"] == "project_scan" and r["input_tokens"] > 0 for r in rows
    ), "expected a usage_ledger record with action='project_scan' and input_tokens>0"


# --------------------------------------------------------------------------- #
# 2. get_relevant_context records usage + cache hit on repeat
# --------------------------------------------------------------------------- #
def test_get_relevant_context_cache_hit(tmp_path):
    app = make_app(tmp_path)
    write_py(
        tmp_path,
        "auth.py",
        "def authenticate(user, password):\n    return user == 'admin' and password == 'secret'\n",
    )
    write_py(
        tmp_path,
        "session.py",
        "def create_session(user_id):\n    return {'user_id': user_id, 'token': 'abc'}\n",
    )
    write_py(tmp_path, "views.py", "def login_view(request):\n    return 'ok'\n")

    app.tool_project_scan()

    first = app.tool_get_relevant_context("login auth", token_budget=400, mode="exploratory")
    second = app.tool_get_relevant_context("login auth", token_budget=400, mode="exploratory")

    # First call: usage with positive input tokens.
    assert "usage" in first
    assert first["usage"]["input_tokens"] > 0

    # Second identical call: cache hit from task_cache.
    assert second.get("cache_hit") is True, "second identical call should hit task_cache"

    # usage_ledger: second get_relevant_context event marked cache_hit=1 with cached_tokens>0.
    ctx_rows = ledger_rows(app, "get_relevant_context")
    assert len(ctx_rows) >= 2, "expected at least 2 get_relevant_context events"
    last = ctx_rows[-1]
    assert last["cache_hit"] == 1, "last get_relevant_context event should have cache_hit=1"
    assert last["cached_tokens"] > 0, "cached event should report cached_tokens>0"


# --------------------------------------------------------------------------- #
# 3. record_decision / memory_search record usage
# --------------------------------------------------------------------------- #
def test_record_decision_and_memory_search_record_usage(tmp_path):
    app = make_app(tmp_path)
    write_py(tmp_path, "app.py", "def login():\n    return True\n")
    app.tool_project_scan()

    app.tool_record_decision("t", "d")
    app.tool_memory_search("login")

    decision_rows = ledger_rows(app, "record_decision")
    assert decision_rows and decision_rows[0]["input_tokens"] > 0

    search_rows = ledger_rows(app, "memory_search")
    assert search_rows and search_rows[0]["input_tokens"] > 0


# --------------------------------------------------------------------------- #
# 4. propose_edit records usage
# --------------------------------------------------------------------------- #
def test_propose_edit_records_usage(tmp_path):
    app = make_app(tmp_path)
    write_py(tmp_path, "app.py", "def login():\n    return True\n")
    app.tool_project_scan()

    app.tool_propose_edit("app.py", "x=1\n")

    propose_rows = ledger_rows(app, "propose_edit")
    assert propose_rows and propose_rows[0]["input_tokens"] > 0


# --------------------------------------------------------------------------- #
# 5. usage_dashboard_data returns real data
# --------------------------------------------------------------------------- #
def test_usage_dashboard_data_real(tmp_path):
    app = make_app(tmp_path)
    write_py(tmp_path, "auth.py", "def authenticate(user):\n    return user is not None\n")
    write_py(tmp_path, "session.py", "def create_session(uid):\n    return uid\n")
    write_py(tmp_path, "views.py", "def login_view(req):\n    return req\n")

    app.tool_project_scan()
    app.tool_record_decision("t", "d")
    app.tool_memory_search("login")
    app.tool_propose_edit("auth.py", "y = 2\n")
    # Trigger a cache hit so cache stats are non-zero.
    app.tool_get_relevant_context("login auth", token_budget=400, mode="exploratory")
    app.tool_get_relevant_context("login auth", token_budget=400, mode="exploratory")

    data = app.tool_usage_dashboard_data()

    assert data["project"]["files"] > 0, "dashboard should report real scanned files"
    assert data["usage"]["total_input_tokens"] > 0
    assert data["usage"]["events"] >= 5, "expected several usage_ledger events"
    assert isinstance(data["top_actions"], list) and len(data["top_actions"]) > 0
    assert isinstance(data["recent_events"], list) and len(data["recent_events"]) > 0

    if data["usage"]["cache_hits"] > 0:
        assert data["usage"]["tokens_saved_by_cache"] > 0
        assert data["usage"]["cache_hit_rate"] > 0


# --------------------------------------------------------------------------- #
# 6. UsageStats.summary aggregates
# --------------------------------------------------------------------------- #
def test_usage_stats_summary_aggregates(tmp_path):
    app = make_app(tmp_path)
    write_py(tmp_path, "app.py", "def login():\n    return True\n")
    app.tool_project_scan()
    app.tool_memory_search("login")

    summary = UsageStats.summary(app.db)

    assert (
        summary["total_tokens"]
        == summary["total_input_tokens"]
        + summary["total_output_tokens"]
        + summary["total_cached_tokens"]
    )
    assert summary["total_tokens"] >= summary["total_input_tokens"]
    assert summary["total_cost_usd"] >= 0


# --------------------------------------------------------------------------- #
# 7. estimate_tokens real behaviour
# --------------------------------------------------------------------------- #
def test_estimate_tokens_real():
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") >= 1
