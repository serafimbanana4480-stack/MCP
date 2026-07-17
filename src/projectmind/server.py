"""Official MCP SDK adapter for ProjectMind domain services."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl

from projectmind import __version__
from projectmind.app import AppContext
from projectmind.errors import ProjectMindError
from projectmind.models.common import HealthStatus
from projectmind.models.execution_models import ApplyPatchResult, CommandResult, PatchProposal
from projectmind.models.server_models import CapabilitiesResult, ProjectStatus, SecurityScanResult
from projectmind.telemetry.self_improvement import ImprovementReport, SelfImprovementReporter

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
LOCAL_STATE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

P = ParamSpec("P")
R = TypeVar("R")
DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)


class StaticTokenVerifier:
    """Constant-time verifier for a user-owned local HTTP bearer token."""

    def __init__(self, expected_token: str) -> None:
        self.expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self.expected_token):
            return None
        return AccessToken(
            token=token,
            client_id="projectmind-local-client",
            scopes=["projectmind"],
            subject="local-user",
        )


def _as_tool_error(exc: Exception) -> ToolError:
    if isinstance(exc, ProjectMindError):
        return ToolError(f"{exc.code}: {exc}")
    return ToolError(f"internal_error: {exc}")


def _project_status(context: AppContext) -> ProjectStatus:
    tables = {
        "workspaces": "workspaces",
        "files": "files",
        "nodes": "nodes",
        "edges": "edges",
        "memories": "memories",
        "plans": "plans",
        "telemetry_events": "telemetry_events",
    }
    counts: dict[str, int] = {}
    with context.database.connect() as connection:
        for key, table in tables.items():
            counts[key] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        proposed = int(
            connection.execute(
                "SELECT COUNT(*) FROM patches WHERE status = 'proposed'"
            ).fetchone()[0]
        )
    return ProjectStatus(
        project_root=str(context.root),
        initialized=True,
        database_path=str(context.database.path),
        index_revision=context.database.index_revision(),
        proposed_patches=proposed,
        **counts,
    )


def create_server(
    project_root: Path | str | None = None,
    *,
    profile: str = "full",
    host: str = "127.0.0.1",
    port: int = 8787,
    http_token: str | None = None,
) -> FastMCP[Any]:
    """Build an isolated server instance suitable for production or SDK tests."""

    context = AppContext.create(project_root)
    auth_settings = None
    token_verifier = None
    if http_token:
        auth_settings = AuthSettings(
            issuer_url=AnyHttpUrl(f"http://{host}:{port}"),
            resource_server_url=AnyHttpUrl(f"http://{host}:{port}/mcp"),
            required_scopes=["projectmind"],
        )
        token_verifier = StaticTokenVerifier(http_token)
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{host}:{port}", f"localhost:{port}"],
        allowed_origins=[f"http://{host}:{port}", f"http://localhost:{port}"],
    )
    server: FastMCP[Any] = FastMCP(
        "ProjectMind",
        instructions=(
            "Use project context and visible engineering plans before proposing changes. "
            "Source mutations require propose_edit followed by explicit confirm_and_apply."
        ),
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        auth=auth_settings,
        token_verifier=token_verifier,
        transport_security=transport_security,
    )

    def tracked_tool(
        *args: Any, **kwargs: Any
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Register a tool with one consistent telemetry boundary."""

        register = cast(
            Callable[[Callable[P, R]], Callable[P, R]], server.tool(*args, **kwargs)
        )

        def decorate(function: Callable[P, R]) -> Callable[P, R]:
            @wraps(function)
            def wrapped(*call_args: P.args, **call_kwargs: P.kwargs) -> R:
                with context.telemetry.measure(function.__name__):
                    return function(*call_args, **call_kwargs)

            return cast(Callable[P, R], register(wrapped))

        return decorate

    @tracked_tool(title="Ping ProjectMind", annotations=READ_ONLY)
    def ping() -> HealthStatus:
        """Validate the MCP handshake, database, and selected project root."""

        return HealthStatus(
            version=__version__,
            project_root=str(context.root),
            database_ready=context.database.path.exists(),
        )

    @tracked_tool(title="Get ProjectMind capabilities", annotations=READ_ONLY)
    def get_capabilities() -> CapabilitiesResult:
        """Describe deterministic and optional capabilities without side effects."""

        return CapabilitiesResult(
            version=__version__,
            capability_mode=context.settings.reasoning.capability_mode,
            tool_profile=profile,
            features={
                "persistence": "sqlite-local",
                "semantic_retrieval": context.settings.embeddings.provider,
                "source_mutation": "propose-confirm-apply",
                "command_execution": "restricted-subprocess",
                "http_auth": "bearer" if http_token else "disabled",
            },
        )

    @tracked_tool(title="Get project status", annotations=READ_ONLY)
    def status() -> ProjectStatus:
        """Return local index, memory, plan, patch, and telemetry counts."""

        return _project_status(context)

    @tracked_tool(title="Propose a source edit", annotations=LOCAL_STATE)
    def propose_edit(
        target: str,
        patch: str,
        patch_format: str = "auto",
    ) -> PatchProposal:
        """Store a reviewable source edit without changing the target file."""

        try:
            return context.patches.propose(target, patch, patch_format=patch_format)
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Confirm and apply a reviewed edit", annotations=DESTRUCTIVE)
    def confirm_and_apply(
        patch_id: str,
        proposal_digest: str,
        confirm: bool = False,
    ) -> ApplyPatchResult:
        """Apply exactly one unchanged, unexpired proposal after explicit confirmation."""

        try:
            return context.patch_applier.apply(
                patch_id,
                proposal_digest,
                confirm=confirm,
            )
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Run a restricted project command", annotations=DESTRUCTIVE)
    def run_command_sandboxed(
        command: list[str],
        confirm: bool = False,
        cwd: str = ".",
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        """Run allowlisted argv without a shell; subprocess mode is restricted."""

        try:
            return context.commands.run(
                command,
                confirm=confirm,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Scan for secrets", annotations=READ_ONLY)
    def scan_secrets(scope: str = ".") -> SecurityScanResult:
        """Scan local text for redacted credential indicators without network access."""

        try:
            findings = context.secrets.scan_scope(scope)
            return SecurityScanResult(
                scanner="projectmind-secrets",
                scope=scope,
                finding_count=len(findings),
                findings=[item.model_dump(mode="json") for item in findings],
            )
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Scan OWASP-oriented patterns", annotations=READ_ONLY)
    def scan_owasp(scope: str = ".") -> SecurityScanResult:
        """Run deterministic local insecure-pattern rules over supported source files."""

        try:
            findings = context.owasp.scan_scope(scope)
            return SecurityScanResult(
                scanner="projectmind-owasp",
                scope=scope,
                finding_count=len(findings),
                findings=[item.model_dump(mode="json") for item in findings],
            )
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Get local usage statistics", annotations=READ_ONLY)
    def get_usage_stats() -> dict[str, object]:
        """Aggregate local, anonymised tool telemetry."""

        return context.telemetry.usage_stats()

    @tracked_tool(title="Generate self-improvement report", annotations=READ_ONLY)
    def self_improvement_report() -> ImprovementReport:
        """Suggest evidence-based improvements; never apply them automatically."""

        return SelfImprovementReporter(context.telemetry).report()

    # ------------------------------------------------------------------
    # Indexing & graph
    # ------------------------------------------------------------------
    @tracked_tool(title="Index a scope", annotations=LOCAL_STATE)
    def index_scope(path: str = ".") -> dict[str, object]:
        """Discover and persist source symbols for a path into the local graph."""

        try:
            with context.telemetry.measure("index_scope"):
                summary = context.indexer.index_scope(path)
            return summary.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Reindex after git pull", annotations=LOCAL_STATE)
    def reindex_on_git_pull(
        old_head: str | None = None, new_head: str = "HEAD"
    ) -> dict[str, object]:
        """Reindex only the files changed by the most recent git pull."""

        try:
            with context.telemetry.measure("reindex_on_git_pull"):
                summary = context.indexer.reindex_on_git_pull(old_head, new_head)
            return summary.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Get graph summary", annotations=READ_ONLY)
    def get_graph_summary(scope: str = ".") -> dict[str, object]:
        """Return file/node/edge counts and language breakdown for a scope."""

        try:
            summary = context.graph.summary(scope)
            return summary.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Find critical files", annotations=READ_ONLY)
    def find_critical_files(top_n: int = 10, scope: str = ".") -> list[dict[str, object]]:
        """Rank files by dependency centrality within the local graph."""

        try:
            nodes = context.graph_analyzer.find_critical_files(top_n=top_n, scope=scope)
            return [node.model_dump(mode="json") for node in nodes]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Detect dependency cycles", annotations=READ_ONLY)
    def detect_dependency_cycles(scope: str = ".") -> list[list[str]]:
        """List canonical dependency cycles in the local graph."""

        try:
            return context.graph_analyzer.detect_dependency_cycles(scope=scope)
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Detect code smells", annotations=READ_ONLY)
    def detect_code_smells(
        scope: str = ".",
        god_class_loc: int = 500,
        god_class_methods: int = 20,
        god_class_fan_out: int = 15,
        shotgun_min_changes: int = 5,
    ) -> list[dict[str, object]]:
        """Heuristically flag god classes, shotgun surgery, and similar smells."""

        try:
            smells = context.graph_analyzer.detect_code_smells(
                scope=scope,
                god_class_loc=god_class_loc,
                god_class_methods=god_class_methods,
                god_class_fan_out=god_class_fan_out,
                shotgun_min_changes=shotgun_min_changes,
            )
            return [smell.model_dump(mode="json") for smell in smells]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Suggest refactoring", annotations=READ_ONLY)
    def suggest_refactoring(node_id: str) -> list[dict[str, object]]:
        """Return ranked refactoring actions for a graph node."""

        try:
            return context.graph_analyzer.suggest_refactoring(node_id)
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Impact analysis", annotations=READ_ONLY)
    def impact_analysis(node_id_or_diff: str) -> dict[str, object]:
        """Estimate the blast radius of changing a node or a unified diff."""

        try:
            result = context.graph_analyzer.impact_analysis(node_id_or_diff)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Parallel impact analysis", annotations=READ_ONLY)
    def parallel_impact_analysis(changes: list[str]) -> list[dict[str, object]]:
        """Run impact analysis for several changes in one call."""

        try:
            results = context.graph_analyzer.parallel_impact_analysis(changes)
            return [result.model_dump(mode="json") for result in results]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Export diagram", annotations=READ_ONLY)
    def export_diagram(scope: str = ".", format: str = "mermaid") -> str:
        """Render the local graph as Mermaid, PlantUML, or Graphviz DOT."""

        try:
            return context.diagrams.export(scope=scope, format=format)
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Simulate a change", annotations=READ_ONLY)
    def simulate_change(proposed_change: str, scope: str = ".") -> dict[str, object]:
        """Disk-free blast-radius simulation over an in-memory graph copy."""

        try:
            from projectmind.graph.simulation import simulate_change as _simulate

            report = _simulate(context.graph, proposed_change, scope=scope)
            return report.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    # ------------------------------------------------------------------
    # Memory & retrieval
    # ------------------------------------------------------------------
    @tracked_tool(title="Record decision", annotations=LOCAL_STATE)
    def record_decision(
        content: str,
        tags: list[str] | None = None,
        related_node_ids: list[str] | None = None,
        branch: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, object]:
        """Persist a durable engineering decision to local memory."""

        try:
            entry = context.memory.record_decision(
                content,
                tags=tags or [],
                related_node_ids=related_node_ids or [],
                branch=branch,
                confidence=confidence,
            )
            return entry.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Record learning", annotations=LOCAL_STATE)
    def record_learning(
        outcome: str,
        what_went_well: str = "",
        what_failed: str = "",
        lessons: str = "",
        tags: list[str] | None = None,
        related_node_ids: list[str] | None = None,
        branch: str | None = None,
        confidence: float | None = None,
    ) -> dict[str, object]:
        """Persist a post-incident learning to local memory."""

        try:
            entry = context.memory.record_learning(
                outcome,
                what_went_well=what_went_well,
                what_failed=what_failed,
                lessons=lessons,
                tags=tags or [],
                related_node_ids=related_node_ids or [],
                branch=branch,
                confidence=confidence,
            )
            return entry.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Search memory", annotations=READ_ONLY)
    def memory_search(
        query: str,
        memory_type: str | None = None,
        min_confidence: float = 0.0,
        branch: str | None = None,
        include_global: bool = True,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        """Lexically search local memory with branch, age, and feedback ranking."""

        try:
            results = context.memory.search(
                query,
                memory_type=memory_type,
                min_confidence=min_confidence,
                branch=branch,
                include_global=include_global,
                tags=tags or [],
                limit=limit,
            )
            return [result.model_dump(mode="json") for result in results]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Consolidate memory", annotations=LOCAL_STATE)
    def consolidate_memory(
        min_cluster_size: int | None = None,
        memory_type: str | None = None,
        branch: str | None = None,
    ) -> dict[str, object]:
        """Cluster and consolidate overlapping local memory entries."""

        try:
            consolidator = context.consolidator
            if min_cluster_size is not None:
                from projectmind.memory.consolidation import DeterministicConsolidator

                consolidator = DeterministicConsolidator(
                    context.memory,
                    min_cluster_size=min_cluster_size,
                )
            result = consolidator.consolidate(
                memory_type=memory_type,
                branch=branch,
            )
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Memory feedback up", annotations=LOCAL_STATE)
    def feedback_thumbs_up(memory_id: str) -> dict[str, object]:
        """Record positive feedback for a memory entry."""

        try:
            entry = context.memory.feedback_thumbs_up(memory_id)
            return entry.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Memory feedback down", annotations=LOCAL_STATE)
    def feedback_thumbs_down(memory_id: str) -> dict[str, object]:
        """Record negative feedback for a memory entry."""

        try:
            entry = context.memory.feedback_thumbs_down(memory_id)
            return entry.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Export memory", annotations=READ_ONLY)
    def export_memory(path: str) -> str:
        """Export validated local memory to a JSON file below the project root."""

        try:
            target = context.memory.export_memory(path)
            return str(target)
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Import memory", annotations=LOCAL_STATE)
    def import_memory(path: str, conflict: str = "skip") -> list[dict[str, object]]:
        """Import a previously exported memory JSON file."""

        try:
            entries = context.memory.import_memory(path, conflict=conflict)  # type: ignore[arg-type]
            return [entry.model_dump(mode="json") for entry in entries]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Verify memory", annotations=LOCAL_STATE)
    def verify_memory(memory_id: str) -> dict[str, object]:
        """Mark a memory entry as verified, restoring its initial confidence."""

        try:
            entry = context.memory.verify_memory(memory_id)
            return entry.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Get relevant context", annotations=READ_ONLY)
    def get_relevant_context(
        task: str,
        mode: str = "surgical",
        token_budget: int = 4_000,
        include_memory: bool = True,
        depth: int = 2,
        branch: str | None = None,
    ) -> dict[str, object]:
        """Assemble explainable, token-budgeted context for a task."""

        try:
            bundle = context.retrieval.get_relevant_context(
                task,
                mode=mode,  # type: ignore[arg-type]
                token_budget=token_budget,
                include_memory=include_memory,
                depth=depth,
                branch=branch,
            )
            return bundle.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Find similar past solutions", annotations=READ_ONLY)
    def find_similar_past_solutions(
        task_description: str, branch: str | None = None, limit: int = 10
    ) -> list[dict[str, object]]:
        """Retrieve analogical past solutions from local memory."""

        try:
            results = context.retrieval.find_similar_past_solutions(
                task_description, branch=branch, limit=limit
            )
            return [result.model_dump(mode="json") for result in results]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    # ------------------------------------------------------------------
    # Reasoning & planning
    # ------------------------------------------------------------------
    @tracked_tool(title="Sequential think", annotations=LOCAL_STATE)
    def sequential_think(task: str, max_steps: int = 8) -> dict[str, object]:
        """Persist a bounded, visible execution checklist for a task."""

        try:
            plan = context.sequential.sequential_think(task, max_steps=max_steps)
            return plan.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Validate plan step", annotations=LOCAL_STATE)
    def validate_step(step_id: str, evidence: str, succeeded: bool = True) -> dict[str, object]:
        """Record externally supplied evidence for a sequential plan step."""

        try:
            step = context.sequential.validate_step(step_id, evidence, succeeded=succeeded)
            return step.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="ReAct step", annotations=LOCAL_STATE)
    def react_step(
        task_id: str, current_thought: str, previous_actions: list[dict[str, object]] | None = None
    ) -> dict[str, object]:
        """Advance a persisted ReAct loop with one observable thought/action."""

        try:
            actions = list(previous_actions or [])
            result = context.react.react_step(task_id, current_thought, previous_actions=actions)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Explore alternatives", annotations=READ_ONLY)
    def explore_alternatives(task: str, num_branches: int = 3) -> dict[str, object]:
        """Return 3-5 challenged implementation alternatives ranked by score."""

        try:
            from projectmind.reasoning.tree_of_thoughts import explore_alternatives as _explore

            result = _explore(task, num_branches=num_branches)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Self reflect", annotations=READ_ONLY)
    def self_reflect(output: str, criteria: str = "") -> list[dict[str, object]]:
        """Critique an output against explicit, deterministic criteria."""

        try:
            critiques = context.self_critique.self_reflect(output, context=criteria)
            return [critique.model_dump(mode="json") for critique in critiques]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Critique plan", annotations=READ_ONLY)
    def critique_plan(plan_id: str) -> list[dict[str, object]]:
        """Critique a persisted sequential plan."""

        try:
            critiques = context.self_critique.critique_plan(plan_id)
            return [critique.model_dump(mode="json") for critique in critiques]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Critique code change", annotations=READ_ONLY)
    def critique_code_change(diff: str, criteria: str = "") -> list[dict[str, object]]:
        """Critique a unified diff against explicit, deterministic criteria."""

        try:
            critiques = context.self_critique.critique_code_change(diff, context=criteria)
            return [critique.model_dump(mode="json") for critique in critiques]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Play devil's advocate", annotations=READ_ONLY)
    def play_devils_advocate(proposal: str) -> dict[str, object]:
        """Surface counter-arguments and risks for a proposal."""

        try:
            from projectmind.reasoning.devils_advocate import play_devils_advocate as _devil

            result = _devil(proposal)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Confidence score", annotations=READ_ONLY)
    def confidence_score(response: str, context: str = "") -> dict[str, object]:
        """Score how well a response is grounded in the supplied context."""

        try:
            from projectmind.reasoning.confidence import confidence_score as _confidence

            result = _confidence(response, context=context)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Hierarchical planning", annotations=LOCAL_STATE)
    def hierarchical_planning(goal: str) -> dict[str, object]:
        """Decompose a goal into a hierarchical plan with checkpoints."""

        try:
            plan = context.planner.hierarchical_planning(goal)
            return plan.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Risk assessment matrix", annotations=READ_ONLY)
    def risk_assessment_matrix(plan_id: str) -> list[dict[str, object]]:
        """Produce hypothesis-labeled delivery risks for a plan."""

        try:
            from projectmind.planning.risk_matrix import risk_assessment_matrix as _risk

            risks = _risk(plan_id, database=context.database)
            return [risk.model_dump(mode="json") for risk in risks]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Create long running task", annotations=LOCAL_STATE)
    def create_long_running_task(spec: str, max_steps: int = 8) -> dict[str, object]:
        """Create a durable long-running task with an attached plan."""

        try:
            task = context.long_tasks.create_long_running_task(spec, max_steps=max_steps)
            return task.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Resume long running task", annotations=LOCAL_STATE)
    def resume_task(task_id: str) -> dict[str, object]:
        """Restore durable state and mark a paused long-running task active."""

        try:
            task = context.long_tasks.resume_task(task_id)
            return task.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Compare implementations", annotations=READ_ONLY)
    def compare_implementations(
        option_a: str,
        option_b: str,
        criteria: list[str],
        evidence_a: dict[str, str] | None = None,
        evidence_b: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Compare two implementation options without inventing a winner."""

        try:
            from projectmind.planning.compare_alternatives import compare_implementations as _cmp

            result = _cmp(
                option_a,
                option_b,
                criteria,
                evidence_a=evidence_a,
                evidence_b=evidence_b,
            )
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Generate boilerplate", annotations=READ_ONLY)
    def generate_boilerplate(
        pattern: str, pattern_context: str, convention_limit: int = 5
    ) -> dict[str, object]:
        """Return review-only boilerplate descriptions for a pattern."""

        try:
            from projectmind.planning.boilerplate import generate_boilerplate as _boiler

            result = _boiler(
                pattern,
                pattern_context,
                memory_store=context.memory,
                convention_limit=convention_limit,
            )
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    # ------------------------------------------------------------------
    # Debugging & quality
    # ------------------------------------------------------------------
    @tracked_tool(title="Detect related bugs", annotations=READ_ONLY)
    def detect_related_bugs(description: str, limit: int = 10) -> list[dict[str, object]]:
        """Retrieve related historical bugs from local memory."""

        try:
            bugs = context.debug.detect_related_bugs(description, limit=limit)
            return [bug.model_dump(mode="json") for bug in bugs]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Root cause analysis", annotations=READ_ONLY)
    def root_cause_analysis(error: str) -> dict[str, object]:
        """Rank evidence-based root-cause candidates for an error trace."""

        try:
            report = context.debug.root_cause_analysis(error)
            return report.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Reproduce issue", annotations=READ_ONLY)
    def reproduce_issue(description: str, error: str) -> dict[str, object]:
        """Generate a review-only regression reproduction proposal."""

        try:
            analysis = context.debug.root_cause_analysis(error)
            proposal = context.repro.propose(description, analysis)
            return proposal.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Run mutation testing", annotations=DESTRUCTIVE)
    def run_mutation_testing(scope: str, confirm: bool = False) -> dict[str, object]:
        """Run the project's mutation-testing adapter over a scope."""

        try:
            result = context.mutation.run(scope, confirm=confirm)
            return result.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Run linters", annotations=DESTRUCTIVE)
    def run_linters(
        scope: str = ".", tool: str | None = None, confirm: bool = False
    ) -> dict[str, object]:
        """Run an allowlisted linter and normalise its diagnostics."""

        try:
            result, diagnostics = context.linters.run(scope, tool=tool, confirm=confirm)
            return {
                "command": result.model_dump(mode="json"),
                "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
            }
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    @tracked_tool(title="Regression analysis", annotations=DESTRUCTIVE)
    def regression_analysis(fix_diff: str, confirm: bool = False) -> list[dict[str, object]]:
        """Plan and run regression tests affected by a fix diff."""

        try:
            plan = context.regression.plan(fix_diff)
            results = context.regression.run(plan, confirm=confirm)
            return [result.model_dump(mode="json") for result in results]
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    # ------------------------------------------------------------------
    # Documentation
    # ------------------------------------------------------------------
    @tracked_tool(title="Update docs", annotations=READ_ONLY)
    def update_docs(scope: str = ".", dry_run: bool = True) -> dict[str, object]:
        """Propose documentation patches from the live graph (never writes)."""

        try:
            from projectmind.documentation.update_docs import update_docs as _update_docs

            proposal = _update_docs(context.graph, scope=scope, dry_run=dry_run)
            return proposal.model_dump(mode="json")
        except Exception as exc:
            raise _as_tool_error(exc) from exc

    return server


def run_server(
    project_root: Path | str | None = None,
    *,
    transport: str = "stdio",
    profile: str = "full",
    host: str = "127.0.0.1",
    port: int = 8787,
    http_token: str | None = None,
) -> None:
    server = create_server(
        project_root,
        profile=profile,
        host=host,
        port=port,
        http_token=http_token,
    )
    if transport not in {"stdio", "streamable-http"}:
        raise ValueError("transport must be stdio or streamable-http")
    server.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    run_server()
