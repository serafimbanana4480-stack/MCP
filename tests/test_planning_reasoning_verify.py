from projectmind.application import ProjectMind
from projectmind.core.exceptions import ProjectMindError


def _make_plan(app: ProjectMind) -> str:
    plan = app.tool_create_plan(
        objective="Implementar autenticação",
        assumptions=["Aplicação web"],
        dependencies=["banco de dados"],
        risks=["SQL injection"],
        mitigations=["parameterized queries"],
        test_strategy=["testes de integração"],
        completion_criteria=["login funciona"],
        steps=[],
    )
    return plan["plan_id"]


def test_create_plan_all_required_fields(tmp_path):
    app = ProjectMind(tmp_path)
    plan = app.tool_create_plan(
        objective="Objetivo",
        assumptions=["a1"],
        dependencies=["d1"],
        risks=["r1"],
        mitigations=["m1"],
        test_strategy=["t1"],
        completion_criteria=["c1"],
        steps=[],
    )
    assert plan["objective"] == "Objetivo"
    assert plan["status"] == "draft"
    assert plan["plan_id"]


def test_validate_plan_blocks_incomplete_plan(tmp_path):
    app = ProjectMind(tmp_path)
    plan = app.tool_create_plan(
        objective="Objetivo",
        assumptions=[],
        dependencies=["d1"],
        risks=["r1"],
        mitigations=["m1"],
        test_strategy=["t1"],
        completion_criteria=["c1"],
        steps=[],
    )
    result = app.tool_validate_plan(plan["plan_id"])
    assert result["valid"] is False
    assert result["status"] == "blocked"
    assert "assumptions" in result["missing"]


def test_validate_plan_valid_complete(tmp_path):
    app = ProjectMind(tmp_path)
    plan_id = _make_plan(app)
    result = app.tool_validate_plan(plan_id)
    assert result["valid"] is True
    assert result["status"] == "validated"


def test_challenge_plan(tmp_path):
    app = ProjectMind(tmp_path)
    plan_id = _make_plan(app)
    result = app.tool_challenge_plan(plan_id)
    assert "challenges" in result
    assert "must_fix" in result


def test_check_completion_blocks_when_incomplete_via_call(tmp_path):
    app = ProjectMind(tmp_path)
    plan_id = _make_plan(app)
    result = app.call("check_completion", {"plan_id": plan_id, "evidence": ["outra coisa"]})
    assert result["status"] == "blocked"


def test_check_completion_passes_when_evidence_matches(tmp_path):
    app = ProjectMind(tmp_path)
    plan_id = _make_plan(app)
    result = app.tool_check_completion(plan_id, evidence=["login funciona"])
    assert result["complete"] is True


def test_hierarchical_planning(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_hierarchical_planning("Objetivo", depth=2)
    assert result["objective"] == "Objetivo"
    assert result["hierarchy"][0]["type"] == "epic"


def test_create_long_running_task(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_create_long_running_task("Objetivo", checkpoints=["c1"])
    assert result["status"] == "active"
    assert result["checkpoints"] == ["c1"]


def test_compare_implementations(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_compare_implementations(
        [
            {"name": "A", "pros": ["p"], "cons": []},
            {"name": "B", "pros": [], "cons": ["c"]},
        ]
    )
    assert result["selected"] == "A"


def test_generate_boilerplate(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_generate_boilerplate("Objetivo", conventions=["c1"])
    assert result["objective"] == "Objetivo"
    assert result["requires_proposal"] is True


def test_risk_assessment_matrix_blocks_unmitigated_high(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_risk_assessment_matrix(
        "plan_x",
        risks=[
            {"title": "vazamento", "probability": 0.9, "impact": 0.9},
        ],
    )
    assert result["blocked"] is True
    assert result["risks"][0]["tier"] in {"high", "critical"}


def test_risk_assessment_matrix_allows_mitigated_high(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_risk_assessment_matrix(
        "plan_x",
        risks=[
            {"title": "vazamento", "probability": 0.9, "impact": 0.9, "mitigation": "WAF"},
        ],
    )
    assert result["blocked"] is False


def test_sequential_think_max_steps_gate(tmp_path):
    app = ProjectMind(tmp_path)
    sid = None
    for _ in range(5):
        r = app.tool_sequential_think("tarefa", max_steps=5, session_id=sid)
        sid = r["session_id"]
    blocked = app.call(
        "sequential_think",
        {"task": "tarefa", "max_steps": 5, "session_id": sid},
    )
    assert blocked["status"] == "blocked"


def test_sequential_think_records_step(tmp_path):
    app = ProjectMind(tmp_path)
    r = app.tool_sequential_think("tarefa", max_steps=10)
    assert r["step_index"] == 1
    assert r["status"] == "passed"


def test_react_step(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_react_step("sess", "pensar", loop_count=0)
    assert result["loop_count"] == 1
    assert result["next_action_type"] == "tool"


def test_explore_alternatives(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_explore_alternatives("proposta", num_branches=3)
    assert len(result["branches"]) == 3
    assert result["selected"] == result["branches"][0]["branch_id"]


def test_self_reflect(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_self_reflect("ref")
    assert "critiques" in result
    assert result["overall_score"] == 70


def test_play_devils_advocate(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_play_devils_advocate("proposta", focus="risco")
    assert result["focus"] == "risco"
    assert "counter_arguments" in result


def test_cognitive_force(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_cognitive_force("pergunta", template="premises")
    assert result["question"] == "pergunta"
    assert result["template"] == "premises"


def test_response_confidence(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_response_confidence("ref", evidence=["e1", "e2"])
    assert result["score"] == 60


def test_record_learning(tmp_path):
    app = ProjectMind(tmp_path)
    result = app.tool_record_learning(
        "task_ref", "successo", lessons=["l1"], applies_to=["a1"]
    )
    assert result["outcome"] == "successo"
    assert result["lessons"] == ["l1"]


def test_validate_step(tmp_path):
    app = ProjectMind(tmp_path)
    ok = app.tool_validate_step({"thought": "t", "success_criteria": ["s"], "status": "passed"})
    assert ok["valid"] is True
    bad = app.tool_validate_step({"thought": "", "success_criteria": []})
    assert bad["valid"] is False


def test_call_unknown_tool_raises_attribute_error(tmp_path):
    import pytest

    app = ProjectMind(tmp_path)
    with pytest.raises(AttributeError):
        app.call("does_not_exist", {})


def test_call_project_mind_error_returns_blocked(tmp_path):
    app = ProjectMind(tmp_path)

    class BoomApp(ProjectMind):
        def tool_boom(self):
            raise ProjectMindError("falha proposital")

    boom = BoomApp(tmp_path)
    result = boom.call("boom", {})
    assert result["status"] == "blocked"
    assert "falha proposital" in result["error"]
