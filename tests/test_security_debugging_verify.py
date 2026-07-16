"""Security & debugging verification tests for ProjectMind.

These tests are designed for environments where pytest cannot be executed
(shell disabled). They are written to be statically inspectable and will
run under pytest where available.

Coverage:
  1. tool_scan_secrets (secrets_guard PATTERNS)
  2. core.security.validate_command (destructive + shell chaining + allowlist)
  3. propose_edit -> critique -> confirm_and_apply gate (double gate)
  4. tool_verify_fix (regression_risk / fixed gates)
  5. Debugging tools sessions/returns
  6. server.create_server: every TOOL_NAMES entry maps to a tool_* method
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from projectmind.application import ProjectMind
from projectmind.core.config import Config
from projectmind.core.exceptions import SecurityViolation
from projectmind.core.security import validate_command
from projectmind.server import TOOL_NAMES, create_server


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def make_app(tmp_path: Path) -> ProjectMind:
    """Build a ProjectMind rooted at tmp_path (isolated sqlite db)."""
    app = ProjectMind(tmp_path)
    # Ensure a writable file exists for edit-apply tests.
    (tmp_path / "app.py").write_text("def login():\n    return True\n", encoding="utf-8")
    return app


def make_config(tmp_path: Path) -> Config:
    return Config.load(tmp_path)


# --------------------------------------------------------------------------- #
# 1. Secrets scanning
# --------------------------------------------------------------------------- #
def test_scan_secrets_detects_aws_key(tmp_path):
    secret = 'aws_key = "AKIAIOSFODNN7EXAMPLE"\n'
    (tmp_path / "config.py").write_text(secret, encoding="utf-8")
    app = ProjectMind(tmp_path)
    res = app.tool_scan_secrets(paths=["config.py"])
    assert res["blocked"] is True
    rules = {f["rule"] for f in res["findings"]}
    assert "aws_key" in rules


def test_scan_secrets_detects_jwt(tmp_path):
    # Header.payload.signature with >=10 chars per segment.
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    (tmp_path / "token.py").write_text(f'token = "{jwt}"\n', encoding="utf-8")
    app = ProjectMind(tmp_path)
    res = app.tool_scan_secrets(paths=["token.py"])
    rules = {f["rule"] for f in res["findings"]}
    assert "jwt" in rules


def test_scan_secrets_via_diff():
    diff = 'password = "supersecretvalue123"\n'
    app = ProjectMind(Path("."))
    res = app.tool_scan_secrets(diff=diff)
    rules = {f["rule"] for f in res["findings"]}
    assert "generic_secret" in rules
    assert res["blocked"] is True


def test_scan_secrets_clean_file(tmp_path):
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    app = ProjectMind(tmp_path)
    res = app.tool_scan_secrets(paths=["clean.py"])
    assert res["findings"] == []
    assert res["blocked"] is False


# --------------------------------------------------------------------------- #
# 2. Command validation (security)
# --------------------------------------------------------------------------- #
def test_validate_command_blocks_rm(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("rm -rf /something", cfg)


def test_validate_command_blocks_git_reset(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("git reset --hard", cfg)


def test_validate_command_blocks_git_clean(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("git clean -fdx", cfg)


def test_validate_command_blocks_shell_and(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("pytest && rm -rf .", cfg)


def test_validate_command_blocks_pipe(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("cat secrets | tee out", cfg)


def test_validate_command_blocks_redirect(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("echo x > /etc/passwd", cfg)


def test_validate_command_accepts_allowlisted(tmp_path):
    cfg = make_config(tmp_path)
    parts = validate_command("pytest -q", cfg)
    assert parts[0] == "pytest"


def test_validate_command_rejects_unallowed_binary(tmp_path):
    cfg = make_config(tmp_path)
    with pytest.raises(SecurityViolation):
        validate_command("curl http://evil", cfg)


# --------------------------------------------------------------------------- #
# 3. Edit gate: propose -> critique -> confirm (double gate)
# --------------------------------------------------------------------------- #
def test_confirm_blocked_without_critique(tmp_path):
    app = make_app(tmp_path)
    proposed = app.tool_propose_edit("app.py", "def login():\n    return False\n")
    blocked = app.call(
        "confirm_and_apply", {"edit_id": proposed["edit_id"], "confirmation": True}
    )
    assert blocked["status"] == "blocked"


def test_confirm_blocked_without_explicit_confirmation(tmp_path):
    app = make_app(tmp_path)
    proposed = app.tool_propose_edit("app.py", "def login():\n    return False\n")
    app.tool_critique_code_change(proposed["edit_id"])
    # confirmation defaults to False -> gate must block.
    blocked = app.tool_confirm_and_apply(proposed["edit_id"], confirmation=False)
    # require() raises -> call() translates to blocked status.
    assert app.call(
        "confirm_and_apply", {"edit_id": proposed["edit_id"], "confirmation": False}
    )["status"] == "blocked"


def test_confirm_applies_after_approve(tmp_path):
    app = make_app(tmp_path)
    proposed = app.tool_propose_edit("app.py", "def login():\n    return False\n")
    critique = app.tool_critique_code_change(proposed["edit_id"])
    assert critique["verdict"] == "approve"
    result = app.tool_confirm_and_apply(proposed["edit_id"], True)
    assert result["applied"] is True
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "def login():\n    return False\n"


def test_propose_edit_blocks_secret(tmp_path):
    app = make_app(tmp_path)
    blocked = app.call(
        "propose_edit", {"file_path": "app.py", "new_content": 'pw = "AKIAIOSFODNN7EXAMPLE"\n'}
    )
    assert blocked["status"] == "blocked"


# --------------------------------------------------------------------------- #
# 4. verify_fix gates
# --------------------------------------------------------------------------- #
def test_verify_fix_blocks_high_risk(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("boom")["session_id"]
    blocked = app.call(
        "verify_fix", {"session_id": sid, "fixed": True, "regression_risk": "high"}
    )
    assert blocked["status"] == "blocked"


def test_verify_fix_blocks_critical_risk(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("boom")["session_id"]
    blocked = app.call(
        "verify_fix", {"session_id": sid, "fixed": True, "regression_risk": "critical"}
    )
    assert blocked["status"] == "blocked"


def test_verify_fix_blocks_unfixed(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("boom")["session_id"]
    blocked = app.call(
        "verify_fix", {"session_id": sid, "fixed": False, "regression_risk": "low"}
    )
    assert blocked["status"] == "blocked"


def test_verify_fix_passes_low_risk_fixed(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("boom")["session_id"]
    res = app.tool_verify_fix(sid, fixed=True, regression_risk="low")
    assert res["fixed"] is True


# --------------------------------------------------------------------------- #
# 5. Debugging tools: sessions + returns
# --------------------------------------------------------------------------- #
def test_debug_start_and_collect_evidence(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("ImportError on startup", stacktrace="Traceback...")[
        "session_id"
    ]
    ev = app.tool_collect_evidence(sid, logs="error log", tests=["test_a"])
    assert "frames" in ev
    assert ev["logs"] == "error log"


def test_root_cause_analysis(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("boom", stacktrace="Traceback (most recent call last):")[
        "session_id"
    ]
    app.tool_collect_evidence(sid)
    rca = app.tool_root_cause_analysis(sid)
    assert "likely_cause" in rca
    assert "confidence" in rca


def test_generate_and_test_hypotheses(tmp_path):
    app = make_app(tmp_path)
    sid = app.tool_debug_start("boom")["session_id"]
    hyp = app.tool_generate_hypotheses(sid)
    assert isinstance(hyp["hypotheses"], list)
    ordered = app.tool_hypothesis_testing_loop(sid)
    assert "ordered" in ordered


def test_detect_related_bugs(tmp_path):
    app = make_app(tmp_path)
    res = app.tool_detect_related_bugs("null pointer crash")
    assert "matches" in res


def test_reproduce_issue(tmp_path):
    app = make_app(tmp_path)
    res = app.tool_reproduce_issue("crash", inputs={"x": 1})
    assert res["status"] == "proposal"


def test_generate_tests(tmp_path):
    app = make_app(tmp_path)
    res = app.tool_generate_tests("src/foo.py", "off by one")
    assert res["test_name"] == "test_regression_case"


def test_static_analysis_blocked_when_destructive(tmp_path):
    app = make_app(tmp_path)
    # 'rm' is not in allowed_commands AND contains destructive token -> blocked.
    res = app.tool_static_analysis("rm -rf .")
    assert res.get("status") == "blocked"


def test_analyze_regression(tmp_path):
    app = make_app(tmp_path)
    res = app.tool_analyze_regression("old", "new", tests=["t1"])
    assert res["regression_risk"] == "low"
    res2 = app.tool_analyze_regression("old", "new")
    assert res2["regression_risk"] == "medium"


# --------------------------------------------------------------------------- #
# 6. server.create_server: TOOL_NAMES -> tool_* methods
# --------------------------------------------------------------------------- #
def test_tool_names_have_methods():
    missing = []
    for name in TOOL_NAMES:
        if not hasattr(ProjectMind, f"tool_{name}"):
            missing.append(name)
    assert missing == [], f"TOOL_NAMES without tool_* method: {missing}"


def test_no_tool_methods_missing_from_tool_names():
    defined = {
        n[len("tool_"):]
        for n in dir(ProjectMind)
        if n.startswith("tool_") and callable(getattr(ProjectMind, n))
    }
    # Methods without a registration are a registration gap (less severe than
    # the reverse, but still worth flagging).
    unregistered = sorted(defined - set(TOOL_NAMES))
    # This assertion documents the gap; currently expected empty.
    assert unregistered == [], f"tool_* methods not registered in TOOL_NAMES: {unregistered}"


def test_create_server_registers_without_attribute_error():
    # If any TOOL_NAME lacks a tool_* method, create_server raises AttributeError
    # at getattr(...) during registration. FastMCP must be importable.
    try:
        create_server(".")
    except RuntimeError:
        pytest.skip("FastMCP not installed; cannot exercise registration")
    except AttributeError as exc:
        pytest.fail(f"create_server failed: missing tool_* method referenced by TOOL_NAMES: {exc}")
