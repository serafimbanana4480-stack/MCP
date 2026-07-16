from projectmind.application import ProjectMind


def test_scan_retrieval_and_gate_bypass_are_safe(tmp_path):
    (tmp_path / "app.py").write_text("def login():\n    return True\n")
    app = ProjectMind(tmp_path)
    assert app.tool_project_scan()["indexed"] == 1
    assert app.tool_find_symbol("login")["symbols"][0]["name"] == "login"
    proposed = app.tool_propose_edit("app.py", "def login():\n    return False\n")
    blocked = app.call("confirm_and_apply", {"edit_id": proposed["edit_id"], "confirmation": True})
    assert blocked["status"] == "blocked"
    critique = app.tool_critique_code_change(proposed["edit_id"])
    assert critique["verdict"] == "approve"
    assert app.tool_confirm_and_apply(proposed["edit_id"], True)["applied"] is True
