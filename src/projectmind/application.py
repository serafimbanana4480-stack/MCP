from __future__ import annotations

import json
import uuid
from pathlib import Path

from .core.config import Config
from .core.db import Database
from .core.exceptions import ProjectMindError
from .core.models import TelemetryEvent
from .core.secrets_guard import scan_files, scan_text
from .core.security import run_sandbox
from .git.diff_parser import unified
from .git.intelligence import info as git_info
from .graph.centrality import critical_files
from .graph.impact import impact
from .graph.refactoring_advisor import suggestions
from .graph.smells import detect_smells
from .graph.store import GraphStore
from .graph.whatif import simulate
from .indexing.scanner import scan
from .memory.branch_memory import set_branch
from .memory.consolidator import consolidate
from .memory.io import export_memory, import_memory
from .memory.store import MemoryStore
from .planning.challenger import challenge
from .planning.compare import compare
from .planning.completion import check
from .planning.scaffolder import boilerplate
from .planning.validator import validate
from .reasoning.cognitive_force import force
from .reasoning.confidence import score
from .reasoning.devils_advocate import challenge as devil_challenge
from .reasoning.gates import require, validate_step
from .reasoning.learning import make_learning
from .reasoning.react import step as react
from .reasoning.reflection import critique_edit, reflect
from .reasoning.risk_matrix import assess
from .reasoning.sequential import next_step
from .reasoning.tree_of_thoughts import explore
from .retrieval.hybrid_retriever import retrieve
from .telemetry.recorder import record
from .telemetry.usage import UsageLedger, UsageStats, estimate_tokens


class ProjectMind:
    def __init__(self, root: str | Path = "."):
        self.config = Config.load(root)
        self.db = Database(self.config.db_path)
        self.memory = MemoryStore(self.db)
        self.graph = GraphStore(self.db)
        self.usage = UsageLedger(self.db)
        self.edits: dict[str, dict] = {}

    def event(
        self, action: str, ref: str = "", justification: str = "", status: str = "ok", **payload
    ) -> None:
        record(
            self.db,
            TelemetryEvent(
                action=action, ref=ref, justification=justification, status=status, payload=payload
            ),
        )

    def summary(self) -> dict:
        files = self.db.rows("SELECT language,COUNT(*) AS count FROM files GROUP BY language")
        frameworks = self.db.rows(
            "SELECT framework,COUNT(*) AS count FROM files WHERE framework IS NOT NULL GROUP BY framework"
        )
        return {
            "root": str(self.config.root),
            "files": self.db.one("SELECT COUNT(*) AS count FROM files")["count"],
            "symbols": self.db.one("SELECT COUNT(*) AS count FROM symbols")["count"],
            "languages": files,
            "frameworks": frameworks,
            "entrypoints": [
                x["path"]
                for x in self.db.rows(
                    "SELECT path FROM files WHERE path LIKE '%main%' OR path LIKE '%app%' LIMIT 10"
                )
            ],
            "risks": detect_smells(self.graph),
            "git": git_info(self.config.root),
        }

    def call(self, name: str, args: dict) -> dict:
        try:
            result = getattr(self, f"tool_{name}")(**args)
            self.event(name, justification="tool invocation")
            return result if isinstance(result, dict) else {"result": result}
        except (ProjectMindError, ValueError, OSError, AttributeError) as exc:
            self.event(name, status="blocked", justification=str(exc))
            return {
                "status": "blocked",
                "error": str(exc),
                "suggested_tool": "inspect_project_state",
            }

    def tool_project_scan(
        self,
        root: str | None = None,
        mode: str = "full",
        scope: str | None = None,
        module: str | None = None,
        include_tests: bool = True,
        reindex_on_pull: bool = True,
    ) -> dict:
        result = scan(
            self.config,
            self.db,
            scope=scope or module,
            incremental=mode == "incremental",
            include_tests=include_tests,
        )
        self.usage.record(
            self.db,
            action="project_scan",
            model="local",
            input_tokens=estimate_tokens(str(result)),
            ref=str(self.config.root),
        )
        return {**result, "root": str(self.config.root), "mode": mode}

    def tool_project_summary(self) -> dict:
        return self.summary()

    def tool_find_symbol(self, query: str, kind: str | None = None, limit: int = 20) -> dict:
        self.usage.record(
            self.db,
            action="find_symbol",
            model="local",
            input_tokens=estimate_tokens(query),
            ref=query[:80],
        )
        clauses = ["(name LIKE ? OR qualified_name LIKE ? OR signature LIKE ?)"]
        params = [f"%{query}%"] * 3
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        params.append(limit)
        return {
            "symbols": self.db.rows(
                f"SELECT symbols.*,files.path FROM symbols JOIN files ON files.id=symbols.file_id WHERE {' AND '.join(clauses)} LIMIT ?",
                params,
            )
        }

    def tool_get_file_overview(self, file_path: str) -> dict:
        path = str(self.config.safe_path(file_path).relative_to(self.config.root)).replace(
            "\\", "/"
        )
        file = self.db.one("SELECT * FROM files WHERE path=?", (path,))
        if not file:
            return {"path": path, "indexed": False}
        file["content"] = file.get("content", "")[:4000]
        return {
            "file": file,
            "symbols": self.db.rows("SELECT * FROM symbols WHERE file_id=?", (file["id"],)),
            "imports": [],
            "exports": [],
            "tests": self.db.rows(
                "SELECT path FROM files WHERE is_test=1 AND content LIKE ?",
                (f"%{Path(path).stem}%",),
            ),
            "decisions": self.memory.search(path, type="decision"),
        }

    def tool_get_relevant_context(
        self,
        task: str,
        token_budget: int,
        mode: str = "exploratory",
        include_memory: bool = True,
        include_tests: bool = True,
        include_git: bool = True,
    ) -> dict:
        require(token_budget > 0, "token_budget é obrigatório e deve ser positivo")
        result = retrieve(self.db, task, token_budget, self.config.weights, mode)
        if include_memory:
            result["memories"] = self.memory.search(task, limit=8)
        result["git"] = git_info(self.config.root) if include_git else None
        input_tokens = estimate_tokens(task) + sum(
            estimate_tokens(f.get("content", "")) for f in result.get("files", [])
        )
        cached = int(result.get("cache_hit", False))
        cached_tokens = input_tokens if cached else 0
        self.usage.record(
            self.db,
            action="get_relevant_context",
            model="gpt-4o",
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            cache_hit=bool(cached),
            ref=task[:80],
            payload={"mode": mode, "files": len(result.get("files", [])), "cache_hit": cached},
        )
        result["usage"] = {
            "input_tokens": input_tokens,
            "cached_tokens": cached_tokens,
            "cache_hit": cached,
        }
        return result

    def tool_impact_analysis(self, target: str, depth: int = 2, include_tests: bool = True) -> dict:
        return impact(self.graph, target, depth)

    def tool_trace_request_flow(self, entrypoint: str, max_depth: int = 5) -> dict:
        return {
            "entrypoint": entrypoint,
            "flow": impact(self.graph, entrypoint, max_depth)["affected_nodes"],
        }

    def tool_critical_files(self, limit: int = 10) -> dict:
        return {"files": critical_files(self.graph, limit)}

    def tool_detect_smells(self) -> dict:
        return {"smells": detect_smells(self.graph)}

    def tool_suggest_refactoring(
        self, rationale: bool = True, expected_impact: bool = True
    ) -> dict:
        return {"suggestions": suggestions(self.graph)}

    def tool_simulate_change(self, target: str, change_type: str, depth: int = 2) -> dict:
        return simulate(self.graph, target, change_type, depth)

    def tool_export_diagram(self, format: str = "mermaid") -> dict:
        return {"format": format, "diagram": self.graph.export(format)}

    def tool_memory_search(
        self,
        query: str,
        type: str | None = None,
        confidence: float = 0,
        provenance: str | None = None,
        limit: int = 10,
    ) -> dict:
        self.usage.record(
            self.db,
            action="memory_search",
            model="local",
            input_tokens=estimate_tokens(query),
            ref=query[:80],
        )
        return {"memories": self.memory.search(query, type, confidence, provenance, limit)}

    def tool_record_decision(
        self,
        title: str,
        decision: str,
        rationale: str = "",
        alternatives: list[str] | None = None,
        confidence: float = 0.9,
        branch: str | None = None,
    ) -> dict:
        self.usage.record(
            self.db,
            action="record_decision",
            model="local",
            input_tokens=estimate_tokens(title),
            ref=title[:80],
        )
        return self.memory.record(
            "decision",
            title,
            decision + (f"\nRationale: {rationale}" if rationale else ""),
            confidence,
            "user_decision",
            branch,
        )

    def tool_record_attempt(self, title: str, body: str, confidence: float = 0.7) -> dict:
        self.usage.record(
            self.db,
            action="record_attempt",
            model="local",
            input_tokens=estimate_tokens(title),
            ref=title[:80],
        )
        return self.memory.record("episodic", title, body, confidence, "test_result")

    def tool_consolidate_memory(self) -> dict:
        return consolidate(self.db)

    def tool_memory_feedback(self, context_ref: str, signal: str, note: str = "") -> dict:
        return self.memory.feedback(context_ref, signal, note)

    def tool_set_branch_memory(self, branch: str, memories: list[str] | None = None) -> dict:
        return set_branch(self.db, branch, memories)

    def tool_export_memory(self) -> dict:
        return {"data": export_memory(self.memory)}

    def tool_import_memory(self, data: str) -> dict:
        return import_memory(self.memory, data)

    def tool_scan_secrets(self, paths: list[str] | None = None, diff: str | None = None) -> dict:
        return {
            "findings": scan_text(diff)
            if diff is not None
            else scan_files(self.config.root, paths),
            "blocked": bool(
                scan_text(diff) if diff is not None else scan_files(self.config.root, paths)
            ),
        }

    def tool_propose_edit(
        self, file_path: str, new_content: str | None = None, diff: str | None = None
    ) -> dict:
        path = self.config.safe_path(file_path)
        old = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        if new_content is None:
            require(bool(diff), "new_content ou diff é obrigatório")
            new_content = old
        findings = scan_text(new_content)
        require(not findings, "segredo ou padrão OWASP detetado", "scan_secrets")
        edit_id = str(uuid.uuid4())
        proposed = {
            "edit_id": edit_id,
            "file_path": str(path.relative_to(self.config.root)),
            "old_content": old,
            "new_content": new_content,
            "diff": unified(old, new_content, str(path)),
            "risks": [],
            "requires_confirmation": True,
        }
        self.edits[edit_id] = proposed
        self.event("propose_edit", edit_id, "user requested edit")
        self.usage.record(
            self.db,
            action="propose_edit",
            model="local",
            input_tokens=estimate_tokens(new_content or diff or ""),
            ref=str(path.relative_to(self.config.root)),
        )
        return proposed

    def tool_critique_code_change(
        self, edit_id: str, perspectives: list[str] | None = None
    ) -> dict:
        edit = self.edits.get(edit_id) or (
            self.db.one(
                "SELECT data FROM critiques WHERE ref=? ORDER BY created_at DESC LIMIT 1",
                (edit_id,),
            )
            and {}
        )
        require(bool(edit), "edit_id não encontrado")
        result = critique_edit(edit, perspectives)
        self.db.execute(
            "INSERT INTO critiques(id,ref,data,verdict,created_at) VALUES(?,?,?,?,datetime('now'))",
            (str(uuid.uuid4()), edit_id, json.dumps(result), result["verdict"]),
        )
        edit["critique_verdict"] = result["verdict"]
        self.edits[edit_id] = edit
        return {"edit_id": edit_id, **result}

    def tool_confirm_and_apply(self, edit_id: str, confirmation: bool = False) -> dict:
        require(confirmation is True, "confirmação explícita é obrigatória")
        edit = self.edits.get(edit_id)
        require(bool(edit), "edit_id não encontrado")
        critique = self.db.one(
            "SELECT verdict FROM critiques WHERE ref=? ORDER BY created_at DESC LIMIT 1", (edit_id,)
        )
        require(
            critique and critique["verdict"] == "approve",
            "confirm_and_apply recusado: critique_code_change aprovado é obrigatório",
        )
        path = self.config.safe_path(edit["file_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(edit["new_content"], encoding="utf-8")
        self.event("confirm_and_apply", edit_id, "explicit confirmation", path=edit["file_path"])
        return {"applied": True, "edit_id": edit_id, "file_path": edit["file_path"]}

    def tool_run_in_sandbox(
        self, command: str, timeout: int | None = None, working_dir: str | None = None
    ) -> dict:
        return run_sandbox(command, self.config, timeout)

    def tool_create_plan(
        self,
        objective: str,
        assumptions: list[str],
        dependencies: list[str],
        risks: list[str],
        mitigations: list[str],
        test_strategy: list[str],
        completion_criteria: list[str],
        steps: list[dict] | None = None,
    ) -> dict:
        from .core.models import VerifiedPlan

        plan = VerifiedPlan(
            objective=objective,
            assumptions=assumptions,
            dependencies=dependencies,
            risks=risks,
            mitigations=mitigations,
            test_strategy=test_strategy,
            completion_criteria=completion_criteria,
            steps=steps or [],
        )
        self.db.execute(
            "INSERT OR REPLACE INTO plans(id,objective,data,status,updated_at) VALUES(?,?,?,?,datetime('now'))",
            (plan.plan_id, objective, plan.model_dump_json(), plan.status),
        )
        return plan.model_dump(mode="json")

    def _plan(self, plan_id: str) -> dict:
        row = self.db.one("SELECT data FROM plans WHERE id=?", (plan_id,))
        require(bool(row), "plano não encontrado")
        return json.loads(row["data"])

    def tool_validate_plan(self, plan_id: str) -> dict:
        plan = self._plan(plan_id)
        result = validate(plan)
        self.db.execute(
            "UPDATE plans SET status=?,updated_at=datetime('now') WHERE id=?",
            (result["status"], plan_id),
        )
        return {"plan_id": plan_id, **result}

    def tool_challenge_plan(self, plan_id: str, perspectives: list[str] | None = None) -> dict:
        return challenge(self._plan(plan_id), perspectives)

    def tool_check_completion(self, plan_id: str, evidence: list[str] | None = None) -> dict:
        result = check(self._plan(plan_id), evidence)
        if result["complete"]:
            self.db.execute("UPDATE plans SET status='done' WHERE id=?", (plan_id,))
        return {"plan_id": plan_id, **result}

    def tool_hierarchical_planning(self, objective: str, depth: int = 3) -> dict:
        return {
            "objective": objective,
            "hierarchy": [
                {
                    "type": "epic",
                    "title": objective,
                    "children": [
                        {
                            "type": "story",
                            "title": "Implementar e verificar",
                            "children": [
                                {
                                    "type": "task",
                                    "title": "Indexar, testar e documentar",
                                    "done_when": ["testes passam"],
                                }
                            ],
                        }
                    ],
                }
            ],
            "depth": depth,
        }

    def tool_create_long_running_task(
        self, objective: str, checkpoints: list[str] | None = None
    ) -> dict:
        return {
            "task_id": str(uuid.uuid4()),
            "objective": objective,
            "checkpoints": checkpoints or ["context", "plan", "edit", "verify"],
            "status": "active",
        }

    def tool_parallel_impact_analysis(self, targets: list[str], depth: int = 2) -> dict:
        return {"targets": targets, "analyses": [impact(self.graph, t, depth) for t in targets]}

    def tool_compare_implementations(self, alternatives: list[dict]) -> dict:
        return compare(alternatives)

    def tool_generate_boilerplate(
        self, objective: str, conventions: list[str] | None = None
    ) -> dict:
        return boilerplate(objective, conventions)

    def tool_debug_start(
        self, symptom: str, stacktrace: str = "", recent_changes: list[str] | None = None
    ) -> dict:
        sid = str(uuid.uuid4())
        data = {
            "session_id": sid,
            "symptom": symptom,
            "stacktrace": stacktrace,
            "recent_changes": recent_changes or [],
            "status": "active",
        }
        self.db.execute(
            "INSERT INTO debug_sessions(id,data,status,updated_at) VALUES(?,?,?,datetime('now'))",
            (sid, json.dumps(data), "active"),
        )
        return data

    def tool_collect_evidence(
        self, session_id: str, logs: str = "", tests: list[str] | None = None
    ) -> dict:
        row = self.db.one("SELECT data FROM debug_sessions WHERE id=?", (session_id,))
        require(bool(row), "sessão de debug não encontrada")
        data = json.loads(row["data"])
        from .debugging.evidence import collect

        ev = collect(data["symptom"], data.get("stacktrace", ""), data.get("recent_changes", []))
        ev.update({"logs": logs, "tests": tests or []})
        data["evidence"] = ev
        self.db.execute(
            "UPDATE debug_sessions SET data=?,updated_at=datetime('now') WHERE id=?",
            (json.dumps(data), session_id),
        )
        return ev

    def _debug(self, sid):
        row = self.db.one("SELECT data FROM debug_sessions WHERE id=?", (sid,))
        require(bool(row), "sessão não encontrada")
        return json.loads(row["data"])

    def tool_root_cause_analysis(self, session_id: str) -> dict:
        from .debugging.engine import root_cause

        return root_cause(self._debug(session_id).get("evidence", self._debug(session_id)))

    def tool_generate_hypotheses(
        self, session_id: str, hypotheses: list[dict] | None = None
    ) -> dict:
        data = self._debug(session_id)
        values = hypotheses or [
            {
                "statement": data["symptom"],
                "probability": 0.6,
                "test_cost": 1,
                "diagnostic_test": "executar teste de reprodução",
            }
        ]
        data["hypotheses"] = values
        self.db.execute(
            "UPDATE debug_sessions SET data=? WHERE id=?", (json.dumps(data), session_id)
        )
        return {"hypotheses": values}

    def tool_hypothesis_testing_loop(self, session_id: str) -> dict:
        from .debugging.hypothesis_tester import prioritize

        return {
            "session_id": session_id,
            "ordered": prioritize(self._debug(session_id).get("hypotheses", [])),
        }

    def tool_verify_fix(
        self,
        session_id: str,
        fixed: bool,
        regression_risk: str = "low",
        evidence: list[str] | None = None,
    ) -> dict:
        require(
            fixed and regression_risk not in {"high", "critical"},
            "verify_fix bloqueado: correção não comprovada ou risco alto",
        )
        return {"fixed": fixed, "regression_risk": regression_risk, "evidence": evidence or []}

    def tool_detect_related_bugs(self, symptom: str) -> dict:
        from .debugging.related_bugs import related

        return {"matches": related(self.memory.search(symptom, limit=50), symptom)}

    def tool_reproduce_issue(self, symptom: str, inputs: dict | None = None) -> dict:
        from .debugging.reproduce import reproduce

        return reproduce(symptom, inputs)

    def tool_generate_tests(self, target: str, symptom: str) -> dict:
        from .debugging.test_gen import generate

        return generate(target, symptom)

    def tool_mutation_testing(self, command: str = "pytest") -> dict:
        return {"status": "proposal", "command": command, "mutants_killed": None}

    def tool_static_analysis(self, command: str = "ruff check .") -> dict:
        from .debugging.static_analysis import analyze

        return analyze(self.config, command)

    def tool_analyze_regression(
        self, before: str, after: str, tests: list[str] | None = None
    ) -> dict:
        from .debugging.regression import analyze

        return analyze(before, after, tests)

    def tool_sequential_think(
        self,
        task: str,
        max_steps: int = 5,
        context_ref: str = "",
        session_id: str | None = None,
        thought: str = "",
        success_criteria: list[str] | None = None,
    ) -> dict:
        sid = session_id or str(uuid.uuid4())
        row = self.db.one("SELECT data FROM reasoning_sessions WHERE id=?", (sid,))
        session = (
            json.loads(row["data"])
            if row
            else {"session_id": sid, "task": task, "steps": [], "status": "active"}
        )
        require(len(session["steps"]) < max_steps, "max_steps atingido")
        result = next_step(
            session, thought or f"Analisar: {task}", success_criteria or ["evidência consultada"]
        )
        require(validate_step(result)["valid"], "validate_step falhou")
        self.db.execute(
            "INSERT OR REPLACE INTO reasoning_sessions(id,data,status,updated_at) VALUES(?,?,?,datetime('now'))",
            (sid, json.dumps(session), session["status"]),
        )
        return {"session_id": sid, **result}

    def tool_react_step(
        self,
        session_id: str,
        thought: str,
        previous_actions: list[dict] | None = None,
        loop_count: int = 0,
    ) -> dict:
        return {"session_id": session_id, **react(thought, previous_actions, loop_count)}

    def tool_explore_alternatives(
        self, proposal: str, num_branches: int = 3, evaluation_axes: list[str] | None = None
    ) -> dict:
        return explore(proposal, num_branches, evaluation_axes)

    def tool_self_reflect(self, output_ref: str, perspectives: list[str] | None = None) -> dict:
        return reflect(output_ref, perspectives)

    def tool_play_devils_advocate(self, proposal: str, focus: str = "risco") -> dict:
        return devil_challenge(proposal, focus)

    def tool_cognitive_force(self, question: str, template: str = "premises") -> dict:
        return force(question, template)

    def tool_response_confidence(self, ref: str, evidence: list[str] | None = None) -> dict:
        return score(ref, evidence)

    def tool_record_learning(
        self,
        task_ref: str,
        outcome: str,
        what_went_well: str = "",
        what_failed: str = "",
        lessons: list[str] | None = None,
        applies_to: list[str] | None = None,
    ) -> dict:
        learning = make_learning(
            task_ref,
            outcome,
            lessons or [],
            what_went_well=what_went_well,
            what_failed=what_failed,
            applies_to=applies_to or [],
        )
        self.db.execute(
            "INSERT INTO learnings(id,task_ref,data,created_at) VALUES(?,?,?,datetime('now'))",
            (str(uuid.uuid4()), task_ref, json.dumps(learning)),
        )
        self.memory.record(
            "semantic", f"Learning: {task_ref}", json.dumps(learning), 0.8, "test_result"
        )
        return learning

    def tool_find_similar_past_solutions(self, task: str, kind: str | None = None) -> dict:
        return {"matches": self.memory.search(task, kind, limit=10)}

    def tool_validate_step(self, step: dict) -> dict:
        return validate_step(step)

    def tool_risk_assessment_matrix(self, plan_id: str, risks: list[dict] | None = None) -> dict:
        return assess(plan_id, risks or [])

    def tool_update_docs(self, summary: str = "") -> dict:
        from .docs.living_docs import update

        return update(self.config.root, summary)

    def tool_self_improve(self) -> dict:
        return {
            "telemetry_events": self.db.one("SELECT COUNT(*) AS count FROM telemetry")["count"],
            "suggestions": ["rever pesos após feedback up/down"],
        }

    def tool_usage_dashboard_data(self) -> dict:
        return {
            "project": {
                "root": str(self.config.root),
                "files": self.db.one("SELECT COUNT(*) c FROM files")["c"],
                "symbols": self.db.one("SELECT COUNT(*) c FROM symbols")["c"],
                "memories": self.db.one("SELECT COUNT(*) c FROM memories")["c"],
                "edges": self.db.one("SELECT COUNT(*) c FROM edges")["c"],
            },
            "usage": UsageStats.summary(self.db),
            "top_actions": self.db.rows(
                "SELECT action, COUNT(*) c, SUM(input_tokens) ti, SUM(cost_usd) cost "
                "FROM usage_ledger GROUP BY action ORDER BY ti DESC LIMIT 10"
            ),
            "recent_events": self.db.rows(
                "SELECT action, model, input_tokens, cached_tokens, cache_hit, cost_usd, created_at "
                "FROM usage_ledger ORDER BY created_at DESC LIMIT 20"
            ),
        }
