from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from projectmind.database import Database
from projectmind.graph.analysis import GraphAnalyzer
from projectmind.graph.diagrams import DiagramExporter
from projectmind.graph.store import GraphStore
from projectmind.indexing.discovery import FileDiscovery
from projectmind.indexing.extractor import Extractor
from projectmind.indexing.git_intelligence import GitIntelligence, parse_unified_diff
from projectmind.indexing.indexer import ProjectIndexer
from projectmind.indexing.monorepo_detector import MonorepoDetector, Workspace
from projectmind.indexing.parsers import ParserRegistry
from projectmind.indexing.watcher import IncrementalWatcher, watch_project
from projectmind.models.graph_models import EdgeType, GraphEdge, NodeType

FIXTURES = Path(__file__).parents[1] / "fixtures" / "indexing"


def copy_fixture(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(FIXTURES / name, target)
    return target


def test_discovery_is_bounded_excluded_and_deterministic(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    oversized = root / "too_big.py"
    oversized.write_text("x" * 128, encoding="utf-8")
    discovery = FileDiscovery(root, max_file_bytes=100)

    first = discovery.discover()
    second = discovery.discover()

    assert [item.relative_path for item in first] == [item.relative_path for item in second]
    assert "too_big.py" not in {item.relative_path for item in first}
    assert all("node_modules" not in item.relative_path for item in first)
    assert all(not item.relative_path.startswith("dist/") for item in first)
    with pytest.raises(ValueError, match="outside project root"):
        discovery.discover(root.parent)


def test_monorepo_detector_deduplicates_and_reads_names(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    workspaces = MonorepoDetector(root).detect()

    assert [(item.path, item.name) for item in workspaces] == [
        (".", "fixture-root"),
        ("apps/web", "fixture-web"),
        ("services/worker", "example.test/worker"),
    ]
    assert len({item.id for item in workspaces}) == 3


def test_python_ast_extracts_symbols_routes_tests_tables_and_imports(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    result = Extractor(root).extract(root / "pkg" / "api.py")

    types = {node.type for node in result.nodes}
    assert {NodeType.FILE, NodeType.MODULE, NodeType.CLASS, NodeType.FUNCTION} <= types
    assert NodeType.TEST in types
    assert NodeType.ROUTE in types
    assert NodeType.DB_TABLE in types
    assert any(
        edge.type is EdgeType.IMPORTS and edge.target_ref == "fastapi" for edge in result.edges
    )
    assert any(edge.type is EdgeType.ROUTES_TO for edge in result.edges)
    assert any(edge.type is EdgeType.TESTS for edge in result.edges)
    assert all((node.start_line or 1) >= 1 for node in result.nodes)


@pytest.mark.parametrize(
    ("filename", "language", "expected_adapter"),
    [
        ("sample.ts", "typescript", "typescript_lexical"),
        ("sample.go", "go", "go_lexical"),
        ("sample.rs", "rust", "rust_lexical"),
        ("Sample.java", "java", "java_lexical"),
    ],
)
def test_parser_registry_has_conservative_fallbacks(
    filename: str, language: str, expected_adapter: str
) -> None:
    source = {
        "typescript": 'import x from "x";\nexport function run() {}',
        "go": 'package main\nimport "fmt"\nfunc run() {}',
        "rust": "use crate::x;\npub fn run() {}",
        "java": "import java.util.List;\npublic class Sample {}",
    }[language]
    result = ParserRegistry().parse(source, filename, language)

    assert result.adapter == expected_adapter
    assert result.confidence < 1.0
    assert result.symbols or result.imports


def test_indexing_is_idempotent_resolves_cycles_and_exports_diagrams(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    database = Database(tmp_path / "graph.db", root)
    indexer = ProjectIndexer(root, database=database)

    first = indexer.index_scope()
    second = indexer.index_scope()

    assert first.files == second.files
    assert first.nodes == second.nodes
    assert first.edges == second.edges
    assert first.index_revision == second.index_revision
    cycles = GraphAnalyzer(indexer.store).detect_dependency_cycles()
    assert len(cycles) == 1
    assert cycles[0][0] == cycles[0][-1]
    assert len(cycles[0]) == 3

    exporter = DiagramExporter(indexer.store)
    assert exporter.to_mermaid().startswith("flowchart LR")
    assert exporter.to_plantuml().endswith("@enduml")
    assert exporter.to_dot().startswith("digraph ProjectMind")
    assert exporter.to_mermaid() == exporter.to_mermaid()


def test_reindex_removes_stale_symbol_and_preserves_incoming_edges(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    indexer = ProjectIndexer(root, database_path=tmp_path / "graph.db")
    indexer.index_scope()
    before = indexer.store.find_nodes("beta")
    assert before
    b_path = root / "pkg" / "b.py"
    b_path.write_text(
        'import pkg.a\n\ndef renamed() -> str:\n    return "beta"\n',
        encoding="utf-8",
    )

    indexer.reindex_paths([b_path])

    assert not indexer.store.find_nodes("beta")
    assert indexer.store.find_nodes("renamed")
    imports = indexer.store.edges(edge_types=(EdgeType.IMPORTS,))
    a_to_b = [edge for edge in imports if edge.target_ref == "pkg.b"]
    assert len(a_to_b) == 1
    assert a_to_b[0].target_id is not None


def test_impact_centrality_and_smells_are_explainable(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "large.py").write_text(
        """def alpha():
    return 1

def beta():
    return 2

class Large:
    def one(self):
        return alpha()

    def two(self):
        return beta()
""",
        encoding="utf-8",
    )
    (root / "consumer.py").write_text("import large\n", encoding="utf-8")
    indexer = ProjectIndexer(root, database_path=tmp_path / "graph.db")
    indexer.index_scope()
    analyzer = GraphAnalyzer(indexer.store)

    scores = analyzer.compute_centrality()
    assert scores and all(0.0 <= score <= 1.0 for score in scores.values())
    large_file = next(
        node for node in indexer.store.nodes(node_types=(NodeType.FILE,)) if node.path == "large.py"
    )
    impact = analyzer.impact_analysis(large_file.id)
    assert impact.direct_dependents
    smells = analyzer.detect_code_smells(
        god_class_loc=4,
        god_class_methods=1,
        god_class_fan_out=1,
    )
    assert any(smell.smell_type == "god_class" for smell in smells)
    assert analyzer.suggest_refactoring(indexer.store.find_nodes("Large")[0].id)


def test_git_hunks_are_parsed_without_invoking_a_shell() -> None:
    hunks = parse_unified_diff(
        """diff --git a/pkg/a.py b/pkg/a.py
--- a/pkg/a.py
+++ b/pkg/a.py
@@ -2,1 +2,3 @@
"""
    )

    assert len(hunks) == 1
    assert hunks[0].path == "pkg/a.py"
    assert hunks[0].new_start == 2
    assert hunks[0].new_end == 4


def test_syntax_errors_and_relative_imports_degrade_gracefully(tmp_path: Path) -> None:
    extractor = Extractor(tmp_path)
    broken = extractor.extract_source("def broken(", "broken.py")
    relative = extractor.extract_source("from . import sibling\n", "pkg/module.py")

    assert broken.parse_status == "partial"
    assert broken.warnings and "parse error" in broken.warnings[0]
    assert broken.file_node.metadata["parser"] == "python_ast"
    assert any(
        edge.type is EdgeType.IMPORTS and edge.target_ref == ".sibling" for edge in relative.edges
    )


def test_typescript_fallback_extracts_nest_and_typeorm(tmp_path: Path) -> None:
    result = Extractor(tmp_path).extract_source(
        """@Entity("users")
export class UsersController {
  @Get("/users")
  async list() {
    return prisma.user.findMany();
  }
}
""",
        "users.ts",
    )

    controller = next(node for node in result.nodes if node.name == "UsersController")
    assert controller.method_count == 1
    assert any(node.type is NodeType.ROUTE for node in result.nodes)
    assert any(node.type is NodeType.DB_TABLE and node.name == "users" for node in result.nodes)


def test_store_workspace_crud_empty_diagrams_and_scope_validation(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    database = Database(tmp_path / "graph.db", root)
    database.initialize()
    store = GraphStore(database)
    workspace = Workspace(
        id="workspace_one",
        path=".",
        kind="python",
        name="one",
        manifest="pyproject.toml",
        metadata={"manifest": "pyproject.toml"},
    )

    assert store.upsert_workspace(workspace)
    assert not store.upsert_workspace(workspace)
    assert store.list_workspaces() == [workspace]
    assert store.list_files() == []
    assert store.chunks() == []
    assert store.get_graph_summary().files == 0
    exporter = DiagramExporter(store)
    assert "empty graph" in exporter.export(format="mermaid")
    assert exporter.export(format="plantuml") == exporter.to_plantuml()
    assert exporter.export(format="dot") == exporter.to_dot()
    with pytest.raises(ValueError, match="unsupported diagram format"):
        exporter.export(format="svg")
    with pytest.raises(ValueError, match="outside project root"):
        store.nodes(scope=root.parent)
    assert store.delete_workspace(workspace.id)
    assert not store.delete_workspace(workspace.id)


def test_file_replacement_rolls_back_on_invalid_edge(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    path = root / "module.py"
    path.write_text("def stable():\n    return True\n", encoding="utf-8")
    database = Database(tmp_path / "graph.db", root)
    database.initialize()
    store = GraphStore(database)
    extraction = Extractor(root).extract(path)
    assert store.replace_file(extraction)
    revision = database.index_revision()
    invalid = replace(
        extraction,
        content_hash="forced-change",
        edges=(
            *extraction.edges,
            GraphEdge(source_id=extraction.file_node.id, type=EdgeType.CALLS),
        ),
    )

    with pytest.raises(ValueError, match="every graph edge"):
        store.replace_file(invalid)

    assert store.file_hash("module.py") == extraction.content_hash
    assert database.index_revision() == revision
    assert store.find_nodes("stable")


def test_git_symbol_diff_and_history_are_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    indexer = ProjectIndexer(root, database_path=tmp_path / "graph.db")
    indexer.index_scope()
    intelligence = GitIntelligence(root, indexer.store)
    symbol_diff = intelligence.symbol_diff(
        diff_text="""--- a/pkg/a.py
+++ b/pkg/a.py
@@ -4,1 +4,1 @@
"""
    )
    assert symbol_diff.available
    assert symbol_diff.files == ("pkg/a.py",)
    assert any(symbol.qualname == "alpha" for symbol in symbol_diff.changed_symbols)

    def fake_git(
        _self: GitIntelligence, arguments: list[str], *, timeout: float = 10.0
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        if arguments[0] == "rev-parse":
            stdout = "true\n"
        elif arguments[0] == "log":
            stdout = "__PM_COMMIT__\npkg/a.py\npkg/b.py\n" * 2
        elif "--name-only" in arguments:
            stdout = "pkg/b.py\npkg/a.py\n"
        else:
            stdout = "+++ b/pkg/a.py\n@@ -1 +1 @@\n"
        return subprocess.CompletedProcess(["git", *arguments], 0, stdout, "")

    monkeypatch.setattr(GitIntelligence, "_git", fake_git)
    assert intelligence.is_repository()
    assert intelligence.changed_files("HEAD~1", "HEAD") == ["pkg/a.py", "pkg/b.py"]
    assert intelligence.files_changed_on_pull("HEAD~1") == ["pkg/a.py", "pkg/b.py"]
    assert intelligence.diff("HEAD~1", "HEAD").startswith("+++")
    assert intelligence.co_change_counts() == {("pkg/a.py", "pkg/b.py"): 2}
    with pytest.raises(ValueError, match="invalid Git revision"):
        intelligence.changed_files("--output=unsafe")


def test_watcher_filters_internal_files_and_reindexes_dependents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    indexer = ProjectIndexer(root, database_path=tmp_path / "graph.db")
    indexer.index_scope()
    watcher = IncrementalWatcher(indexer, debounce_ms=0)
    b_path = root / "pkg" / "b.py"
    changes = {
        (1, str(b_path)),
        (1, str(root / ".projectmind" / "projectmind.db-wal")),
        (1, str(root / "dist" / "generated.js")),
    }

    assert watcher.filter_paths(changes) == ["pkg/b.py"]
    assert "pkg/a.py" in watcher.impacted_paths(changes)
    assert watcher.process_changes([]) is None

    async def fake_awatch(*_args: object, **_kwargs: object):
        yield {(1, str(b_path))}

    watchfiles = types.ModuleType("watchfiles")
    watchfiles.awatch = fake_awatch
    monkeypatch.setitem(sys.modules, "watchfiles", watchfiles)
    asyncio.run(watcher.watch())
    asyncio.run(watch_project(indexer, debounce_ms=0))


def test_batch_impact_critical_files_cycles_and_shotgun_history(tmp_path: Path) -> None:
    root = copy_fixture(tmp_path, "monorepo")
    indexer = ProjectIndexer(root, database_path=tmp_path / "graph.db")
    indexer.index_scope()
    co_changes = {
        ("pkg/b.py", "pkg/api.py"): 7,
        ("pkg/b.py", "apps/web/src/server.ts"): 6,
        ("pkg/b.py", "services/worker/main.go"): 5,
    }
    analyzer = GraphAnalyzer(indexer.store, co_change_counts=co_changes)
    a_file = next(
        node for node in indexer.store.nodes(node_types=(NodeType.FILE,)) if node.path == "pkg/a.py"
    )

    assert analyzer.find_critical_files(top_n=2)
    assert analyzer.find_critical_files(top_n=0) == []
    with pytest.raises(ValueError, match="top_n"):
        analyzer.find_critical_files(top_n=-1)
    assert analyzer.detect_dependency_cycles()
    findings = analyzer.detect_code_smells()
    assert any(item.smell_type == "cyclic_dependency" for item in findings)
    assert any(item.smell_type == "shotgun_surgery" for item in findings)
    diff_impact = analyzer.impact_analysis("+++ b/pkg/a.py\n@@ -1 +1 @@\n")
    assert diff_impact.target.startswith("+++")
    assert len(analyzer.parallel_impact_analysis([a_file.id, "missing"])) == 2
