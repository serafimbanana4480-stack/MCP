from __future__ import annotations

import json
from pathlib import Path

import pytest

from projectmind.database import Database
from projectmind.errors import ConflictError
from projectmind.memory.store import MemoryStore
from projectmind.models.memory_models import MemoryType
from projectmind.models.reasoning_models import StepStatus
from projectmind.planning.boilerplate import generate_boilerplate
from projectmind.planning.compare_alternatives import compare_implementations
from projectmind.planning.hierarchical_planning import HierarchicalPlanner
from projectmind.planning.long_running_tasks import LongRunningTaskService
from projectmind.planning.risk_matrix import risk_assessment_matrix
from projectmind.reasoning.confidence import confidence_score
from projectmind.reasoning.devils_advocate import play_devils_advocate
from projectmind.reasoning.post_mortem import record_learning
from projectmind.reasoning.react_loop import ReActLoop
from projectmind.reasoning.self_critique import critique_code_change, critique_plan, self_reflect
from projectmind.reasoning.sequential_thinking import SequentialThinkingEngine
from projectmind.reasoning.similar_solutions import find_similar_past_solutions
from projectmind.reasoning.tree_of_thoughts import explore_alternatives


@pytest.fixture
def database(tmp_path: Path) -> Database:
    value = Database(tmp_path / "state.db", tmp_path)
    value.initialize()
    return value


def test_sequential_plan_is_durable_visible_and_strictly_validated(database: Database) -> None:
    engine = SequentialThinkingEngine(database)
    plan = engine.sequential_think("Add a durable audit endpoint", max_steps=4)

    assert len(plan.steps) == 4
    assert plan.capability_mode == "deterministic"
    assert "private reasoning" in plan.prompt_template
    assert all(step.success_criteria and step.status is StepStatus.PENDING for step in plan.steps)

    with pytest.raises(ConflictError, match="earlier step"):
        engine.validate_step(plan.steps[1].id, "pytest passed")

    first = engine.validate_step(plan.steps[0].id, "Scope reviewed in ticket PM-1")
    assert first.status is StepStatus.VALIDATED
    failed = engine.validate_step(
        plan.steps[1].id,
        "Architecture review found an unresolved dependency",
        succeeded=False,
    )
    assert failed.status is StepStatus.FAILED

    restarted = SequentialThinkingEngine(database).get_plan(plan.plan_id)
    assert restarted.steps[0].evidence == "Scope reviewed in ticket PM-1"
    assert restarted.steps[1].status is StepStatus.FAILED
    with database.connect() as connection:
        status = connection.execute(
            "SELECT status FROM plans WHERE id = ?", (plan.plan_id,)
        ).fetchone()[0]
    assert status == "needs_revision"


def test_react_loop_is_bounded_and_does_not_persist_current_thought(database: Database) -> None:
    first = ReActLoop(database, max_iterations=2).react_step(
        "task-1", "private free-form rationale must not be stored", []
    )
    assert first.iteration == 1
    assert first.should_stop is False

    second = ReActLoop(database, max_iterations=2).react_step(
        "task-1",
        "another private rationale",
        [{"action": "context inspected", "analysis": "private mapping rationale"}],
    )
    assert second.iteration == 2
    assert second.should_stop is True
    assert second.warning and "limit" in second.warning
    with database.connect() as connection:
        state_json = str(
            connection.execute(
                "SELECT state_json FROM react_states WHERE task_id = 'task-1'"
            ).fetchone()[0]
        )
    state = json.loads(state_json)
    assert state["persisted_fields"] == "observable_actions_only"
    assert "private rationale" not in state_json
    assert "private mapping rationale" not in state_json

    already_stopped = ReActLoop(database, max_iterations=2).react_step(
        "task-1", "ignored after stop", []
    )
    assert already_stopped.iteration == 2
    assert already_stopped.should_stop is True
    assert already_stopped.suggested_action == "reset_react_loop"

    incomplete = ReActLoop(database, max_iterations=3).react_step(
        "task-incomplete", "continue", ["validation is incomplete"]
    )
    assert incomplete.should_stop is False


@pytest.mark.parametrize("branches", [3, 4, 5])
def test_alternatives_are_distinct_ranked_and_capability_honest(branches: int) -> None:
    result = explore_alternatives("Move session storage", branches)

    assert len(result.alternatives) == branches
    assert len({alternative.title for alternative in result.alternatives}) == branches
    assert result.recommended_index == 0
    assert result.capability_mode == "deterministic"
    assert "repository evidence" in result.recommendation
    assert [item.confidence.score for item in result.alternatives] == sorted(
        (item.confidence.score for item in result.alternatives), reverse=True
    )
    assert all(item.pros and item.cons and item.risks for item in result.alternatives)


def test_alternatives_reject_out_of_contract_branch_count() -> None:
    with pytest.raises(ValueError, match="between 3 and 5"):
        explore_alternatives("Move session storage", 2)


def test_reflection_and_code_critique_always_use_four_perspectives(database: Database) -> None:
    critiques = self_reflect("Propose a module change", "No test output is available")
    assert [item.perspective for item in critiques] == [
        "Architect",
        "Security",
        "Test Engineer",
        "Performance",
    ]

    dangerous = critique_code_change("+ result = eval(user_input)")
    security = next(item for item in dangerous if item.perspective == "Security")
    assert security.severity == "high"
    assert any("eval" in issue for issue in security.issues)

    plan = SequentialThinkingEngine(database).sequential_think("Add endpoint", max_steps=3)
    plan_critiques = critique_plan(plan.plan_id, database=database)
    assert len(plan_critiques) == 4
    assert any("not been validated" in issue for issue in plan_critiques[0].issues)


def test_devils_advocate_and_confidence_are_structured_and_calibrated() -> None:
    challenged = play_devils_advocate("Replace all session storage in one release")
    assert len(challenged.counterarguments) == 5
    assert {item.category for item in challenged.counterarguments} >= {
        "Assumptions",
        "Rollback",
        "Simpler alternative",
    }
    assert "hypotheses" in challenged.caveat

    unsupported = confidence_score("This is guaranteed and cannot fail.")
    supported = confidence_score(
        "Changed src/projectmind/example.py:12; rollback remains available. pytest passed.",
        "The assumption is explicitly marked unknown.",
    )
    assert unsupported.score < supported.score
    assert supported.supporting_evidence
    assert "not a probability" in supported.justification


def test_similar_solution_boundary_uses_memory_without_semantic_overclaim(
    database: Database,
) -> None:
    store = MemoryStore(database)
    stored = store.create(
        "Redis session migration used a compatibility adapter and staged rollout.",
        memory_type=MemoryType.LESSON,
        summary="Staged Redis session migration",
    )

    result = find_similar_past_solutions("Redis session migration", memory_store=store, limit=3)
    assert [solution.memory_id for solution in result.solutions] == [stored.id]
    assert result.capability_mode == "deterministic"
    assert "not embedding similarity" in result.search_note

    unavailable = find_similar_past_solutions("Redis session migration")
    assert unavailable.solutions == []
    assert "No similarity adapter" in unavailable.search_note


def test_post_mortem_calls_memory_store_when_available(database: Database) -> None:
    transient = record_learning("Delivered", "Small reviews", "One retry", "Validate first")
    assert transient.persisted is False
    assert transient.memory_id is None

    store = MemoryStore(database)
    durable = record_learning(
        "Delivered",
        "Small reviews",
        "One retry",
        "Validate first",
        memory_store=store,
    )
    assert durable.persisted is True
    assert durable.memory_id is not None
    assert store.get(durable.memory_id).type is MemoryType.LESSON


def test_hierarchical_plan_has_epic_story_task_links_and_persisted_identity(
    database: Database,
) -> None:
    plan = HierarchicalPlanner(database).hierarchical_planning("Ship an auditable endpoint")
    by_id = {task.id: task for task in plan.tasks}
    levels = {task.level for task in plan.tasks}

    assert levels == {"epic", "story", "technical_task"}
    assert len([task for task in plan.tasks if task.level == "epic"]) == 1
    assert all(task.parent_id in by_id for task in plan.tasks if task.parent_id is not None)
    assert all(task.success_criteria for task in plan.tasks)
    with database.connect() as connection:
        persisted = connection.execute(
            "SELECT task FROM plans WHERE id = ?", (plan.plan_id,)
        ).fetchone()
    assert persisted is not None


def test_risk_matrix_is_sorted_and_score_is_probability_times_impact(
    database: Database,
) -> None:
    plan = HierarchicalPlanner(database).hierarchical_planning("Migrate storage")
    risks = risk_assessment_matrix(plan.plan_id, database=database)

    assert len(risks) >= 4
    assert [risk.score for risk in risks] == sorted((risk.score for risk in risks), reverse=True)
    assert all(risk.score == risk.probability * risk.impact for risk in risks)
    assert all(risk.mitigation for risk in risks)


def test_long_task_resumes_after_service_restart_and_enforces_post_mortem(
    database: Database,
) -> None:
    store = MemoryStore(database)
    first_process = LongRunningTaskService(database, memory_store=store)
    created = first_process.create_long_running_task("Implement durable session migration")
    first_process.add_checkpoint(created.id, "Architecture context captured")
    first_process.pause_task(created.id)

    restarted = LongRunningTaskService(database, memory_store=store)
    resumed = restarted.resume_task(created.id)
    assert resumed.status == "active"
    assert resumed.checkpoints == ["Architecture context captured"]
    assert resumed.plan_id == created.plan_id

    with pytest.raises(ConflictError, match="post-mortem gate"):
        restarted.close_task(created.id)

    closed = restarted.close_task(
        created.id,
        outcome="Migration delivered",
        what_went_well="Checkpoints survived restart",
        what_failed="Initial validation failed",
        lessons="Persist observable progress before every boundary",
    )
    assert closed.status == "completed"
    assert closed.post_mortem_memory_id is not None
    assert store.get(closed.post_mortem_memory_id).type is MemoryType.LESSON


def test_comparison_is_structured_without_inventing_a_winner() -> None:
    comparison = compare_implementations(
        "Redis",
        "PostgreSQL",
        ["latency", "operational cost"],
        evidence_a={"latency": "p95 measured at 4 ms"},
        evidence_b={"operational cost": "uses the existing managed database"},
    )

    assert comparison.criteria == ["latency", "operational cost"]
    assert comparison.advantages_a == ["latency: supplied evidence - p95 measured at 4 ms"]
    assert comparison.advantages_b == [
        "operational cost: supplied evidence - uses the existing managed database"
    ]
    assert "No evidence-based winner" in comparison.recommendation
    assert "unknown" in comparison.estimated_cost_a


def test_boilerplate_is_convention_aware_description_only(database: Database) -> None:
    store = MemoryStore(database)
    convention = store.create(
        "FastAPI endpoint modules delegate to services and keep routers thin.",
        memory_type=MemoryType.CONVENTION,
        summary="Thin FastAPI endpoint convention",
    )

    proposal = generate_boilerplate(
        "FastAPI endpoint",
        "Create a session endpoint that delegates to the session service",
        memory_store=store,
    )

    assert proposal.writes_files is False
    assert len(proposal.artifacts) == 3
    assert [item.memory_id for item in proposal.conventions_used] == [convention.id]
    assert "not generated file contents" in proposal.description
    assert all(not hasattr(artifact, "content") for artifact in proposal.artifacts)
