"""Composition root for domain services shared by MCP, CLI, and dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from projectmind.config import ProjectMindSettings
from projectmind.database import Database
from projectmind.execution.confirm_and_apply import PatchApplier
from projectmind.execution.propose_edit import PatchService
from projectmind.execution.safe_subprocess import RestrictedCommandRunner
from projectmind.graph.analysis import GraphAnalyzer
from projectmind.graph.builder import GraphBuilder
from projectmind.graph.diagrams import DiagramExporter
from projectmind.graph.store import GraphStore
from projectmind.indexing.git_intelligence import GitIntelligence
from projectmind.indexing.indexer import ProjectIndexer
from projectmind.memory.consolidation import DeterministicConsolidator
from projectmind.memory.store import MemoryStore
from projectmind.planning.hierarchical_planning import HierarchicalPlanner
from projectmind.planning.long_running_tasks import LongRunningTaskManager
from projectmind.quality.linters_bridge import LintersBridge
from projectmind.quality.mutation_testing import MutationTestingService
from projectmind.quality.regression_analysis import RegressionAnalyzer
from projectmind.quality.related_bugs import DebugService
from projectmind.quality.repro_generator import ReproductionGenerator
from projectmind.reasoning.react_loop import ReActLoop
from projectmind.reasoning.self_critique import SelfCritiqueEngine
from projectmind.reasoning.sequential_thinking import SequentialThinkingEngine
from projectmind.retrieval.context_builder import RetrievalEngine
from projectmind.security.owasp_rules import OwaspScanner
from projectmind.security.secrets_scanner import SecretScanner
from projectmind.telemetry.events import TelemetryStore


@dataclass(slots=True)
class AppContext:
    root: Path
    settings: ProjectMindSettings
    database: Database
    patches: PatchService
    patch_applier: PatchApplier
    commands: RestrictedCommandRunner
    secrets: SecretScanner
    owasp: OwaspScanner
    telemetry: TelemetryStore
    graph: GraphStore
    graph_builder: GraphBuilder
    graph_analyzer: GraphAnalyzer
    diagrams: DiagramExporter
    indexer: ProjectIndexer
    git: GitIntelligence
    memory: MemoryStore
    consolidator: DeterministicConsolidator
    retrieval: RetrievalEngine
    sequential: SequentialThinkingEngine
    react: ReActLoop
    self_critique: SelfCritiqueEngine
    long_tasks: LongRunningTaskManager
    planner: HierarchicalPlanner
    debug: DebugService
    linters: LintersBridge
    mutation: MutationTestingService
    regression: RegressionAnalyzer
    repro: ReproductionGenerator

    @classmethod
    def create(
        cls,
        project_root: Path | str | None = None,
        *,
        initialize: bool = True,
    ) -> AppContext:
        root, settings = ProjectMindSettings.load(project_root)
        database = Database(root / ".projectmind" / "projectmind.db", root)
        if initialize:
            database.initialize()
        graph = GraphStore(database)
        memory = MemoryStore(database, settings.memory)
        retrieval = RetrievalEngine(database, memory, settings.retrieval)
        return cls(
            root=root,
            settings=settings,
            database=database,
            patches=PatchService(database, root, settings),
            patch_applier=PatchApplier(database, root),
            commands=RestrictedCommandRunner(root, settings),
            secrets=SecretScanner(root),
            owasp=OwaspScanner(root),
            telemetry=TelemetryStore(database, settings),
            graph=graph,
            graph_builder=GraphBuilder(graph),
            graph_analyzer=GraphAnalyzer(graph),
            diagrams=DiagramExporter(graph),
            indexer=ProjectIndexer(root, database, config=settings),
            git=GitIntelligence(root, graph),
            memory=memory,
            consolidator=DeterministicConsolidator(memory),
            retrieval=retrieval,
            sequential=SequentialThinkingEngine(database),
            react=ReActLoop(database, max_iterations=settings.reasoning.max_react_iterations),
            self_critique=SelfCritiqueEngine(database),
            long_tasks=LongRunningTaskManager(
                database,
                memory_store=memory,
                require_post_mortem=settings.reasoning.require_post_mortem_on_task_close,
            ),
            planner=HierarchicalPlanner(database),
            debug=DebugService(database, root),
            linters=LintersBridge(root, RestrictedCommandRunner(root, settings)),
            mutation=MutationTestingService(root, RestrictedCommandRunner(root, settings)),
            regression=RegressionAnalyzer(database, root, RestrictedCommandRunner(root, settings)),
            repro=ReproductionGenerator(root),
        )

