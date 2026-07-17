"""Explainable architectural graph analyses."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

import networkx as nx

from projectmind.graph.store import GraphStore
from projectmind.models.graph_models import (
    CodeSmell,
    EdgeType,
    GraphNode,
    ImpactResult,
    NodeType,
)

DEPENDENCY_EDGES: tuple[EdgeType, ...] = (EdgeType.IMPORTS, EdgeType.CALLS)
IMPACT_EDGES: tuple[EdgeType, ...] = (
    EdgeType.IMPORTS,
    EdgeType.CALLS,
    EdgeType.INHERITS,
    EdgeType.TESTS,
    EdgeType.ROUTES_TO,
    EdgeType.READS_WRITES_TABLE,
)


class GraphAnalyzer:
    def __init__(
        self,
        store: GraphStore,
        *,
        co_change_counts: Mapping[tuple[str, str], int] | None = None,
    ) -> None:
        self.store = store
        self.co_change_counts = dict(co_change_counts or {})

    def compute_centrality(self, scope: str = ".") -> dict[str, float]:
        graph = self.store.to_networkx(scope=scope, edge_types=DEPENDENCY_EDGES)
        if not graph:
            return {}
        if graph.number_of_edges() == 0:
            value = 1.0 / graph.number_of_nodes()
            scores = {str(node_id): value for node_id in graph.nodes}
        else:
            try:
                computed = nx.pagerank(graph, alpha=0.85, max_iter=200, tol=1.0e-12)
            except ImportError:
                computed = self._pagerank_without_scipy(graph)
            scores = {str(node_id): float(score) for node_id, score in computed.items()}
        # PageRank is already in [0,1].  Clamp tiny floating-point drift and
        # persist derived values without changing the content revision.
        normalised = {
            node_id: min(1.0, max(0.0, score)) for node_id, score in sorted(scores.items())
        }
        self.store.update_centrality(normalised)
        return normalised

    @staticmethod
    def _pagerank_without_scipy(
        graph: nx.DiGraph, *, alpha: float = 0.85, iterations: int = 200
    ) -> dict[object, float]:
        """Small power iteration fallback for minimal NetworkX installations."""

        count = graph.number_of_nodes()
        if not count:
            return {}
        score = {node: 1.0 / count for node in graph.nodes}
        for _ in range(iterations):
            dangling_score = sum(score[node] for node in graph if graph.out_degree(node) == 0)
            dangling = alpha * dangling_score / count
            updated = {node: (1.0 - alpha) / count + dangling for node in graph}
            for source in graph:
                successors = list(graph.successors(source))
                if not successors:
                    continue
                total_weight = sum(
                    float(graph[source][target].get("weight", 1.0)) for target in successors
                )
                for target in successors:
                    weight = float(graph[source][target].get("weight", 1.0))
                    updated[target] += alpha * score[source] * weight / total_weight
            error = sum(abs(updated[node] - score[node]) for node in graph)
            score = updated
            if error < 1.0e-12 * count:
                break
        return score

    def find_critical_files(self, top_n: int = 10, scope: str = ".") -> list[GraphNode]:
        if top_n < 0:
            raise ValueError("top_n cannot be negative")
        scores = self.compute_centrality(scope)
        graph = self.store.to_networkx(scope=scope, edge_types=DEPENDENCY_EDGES)
        ranked: list[GraphNode] = []
        for file_node in self.store.nodes(scope=scope, node_types=(NodeType.FILE,)):
            path_ids = [
                str(node_id)
                for node_id, data in graph.nodes(data=True)
                if isinstance(data.get("node"), GraphNode) and data["node"].path == file_node.path
            ]
            aggregate = sum(scores.get(node_id, 0.0) for node_id in path_ids)
            ranked.append(file_node.model_copy(update={"centrality": min(1.0, aggregate)}))
        return sorted(
            ranked,
            key=lambda node: (-(node.centrality or 0.0), node.path, node.id),
        )[:top_n]

    def detect_dependency_cycles(self, scope: str = ".") -> list[list[str]]:
        graph = self.store.to_networkx(scope=scope, edge_types=DEPENDENCY_EDGES)
        canonical: set[tuple[str, ...]] = set()
        for cycle in nx.simple_cycles(graph):
            values = [str(item) for item in cycle]
            if not values:
                continue
            rotations = [tuple(values[index:] + values[:index]) for index in range(len(values))]
            canonical.add(min(rotations))
        return [[*cycle, cycle[0]] for cycle in sorted(canonical)]

    def detect_code_smells(
        self,
        scope: str = ".",
        *,
        god_class_loc: int = 500,
        god_class_methods: int = 20,
        god_class_fan_out: int = 15,
        shotgun_min_changes: int = 5,
        persist: bool = True,
    ) -> list[CodeSmell]:
        graph = self.store.to_networkx(scope=scope, edge_types=DEPENDENCY_EDGES)
        nodes = {node.id: node for node in self.store.nodes(scope=scope)}
        findings: list[CodeSmell] = []

        for node in sorted(nodes.values(), key=lambda item: item.id):
            if node.type is not NodeType.CLASS:
                continue
            descendants = self._contained_descendants(node.id, scope)
            sources = {node.id, *descendants}
            targets = {
                target
                for source in sources
                if source in graph
                for target in graph.successors(source)
                if target not in sources
            }
            fan_out = len(targets)
            if (
                (node.loc or 0) > god_class_loc
                and node.method_count > god_class_methods
                and fan_out > god_class_fan_out
            ):
                findings.append(
                    CodeSmell(
                        node_id=node.id,
                        smell_type="god_class",
                        severity="high",
                        description=(
                            f"{node.qualname} has {node.loc or 0} lines, "
                            f"{node.method_count} methods "
                            f"and fan-out {fan_out}."
                        ),
                        suggestion=(
                            "Split cohesive responsibilities into smaller services "
                            "or domain objects."
                        ),
                        evidence={
                            "loc": node.loc or 0,
                            "method_count": node.method_count,
                            "fan_out": fan_out,
                            "thresholds": {
                                "loc": god_class_loc,
                                "method_count": god_class_methods,
                                "fan_out": god_class_fan_out,
                            },
                        },
                    )
                )

        coupling: dict[str, tuple[int, int, int]] = {}
        for node_id in graph.nodes:
            afferent = graph.in_degree(node_id)
            efferent = graph.out_degree(node_id)
            coupling[str(node_id)] = (afferent, efferent, afferent * efferent)
        positive = sorted(value[2] for value in coupling.values() if value[2] > 0)
        p90 = self._percentile_nearest_rank(positive, 0.90)
        if p90 > 0:
            for node_id, (afferent, efferent, product) in sorted(coupling.items()):
                if product <= p90:
                    continue
                found = nodes.get(node_id)
                if found is None:
                    continue
                findings.append(
                    CodeSmell(
                        node_id=node_id,
                        smell_type="tight_coupling",
                        severity="medium" if product < p90 * 2 else "high",
                        description=(
                            f"{found.qualname} has high bidirectional coupling "
                            f"({afferent} incoming x {efferent} outgoing = {product})."
                        ),
                        suggestion=(
                            "Introduce a stable interface or invert one dependency direction."
                        ),
                        evidence={
                            "afferent": afferent,
                            "efferent": efferent,
                            "score": product,
                            "p90": p90,
                        },
                    )
                )

        for cycle in self.detect_dependency_cycles(scope):
            for node_id in cycle[:-1]:
                found = nodes.get(node_id)
                if found is None:
                    continue
                findings.append(
                    CodeSmell(
                        node_id=node_id,
                        smell_type="cyclic_dependency",
                        severity="high",
                        description=f"{found.qualname} participates in a dependency cycle.",
                        suggestion=(
                            "Break the cycle through dependency inversion or a shared "
                            "lower-level module."
                        ),
                        evidence={"cycle": cycle},
                    )
                )

        path_to_file = {node.path: node for node in nodes.values() if node.type is NodeType.FILE}
        cochange_totals: dict[str, list[tuple[str, int]]] = {}
        for (left, right), count in sorted(self.co_change_counts.items()):
            if count >= shotgun_min_changes:
                cochange_totals.setdefault(left, []).append((right, count))
                cochange_totals.setdefault(right, []).append((left, count))
        for path, partners in sorted(cochange_totals.items()):
            # Report only broad historical scattering (three or more files) and
            # only when no direct static relationship explains the co-change.
            found = path_to_file.get(path)
            if found is None:
                continue
            unexplained = [
                (partner, count)
                for partner, count in partners
                if (other := path_to_file.get(partner)) is not None
                and not graph.has_edge(node.id, other.id)
                and not graph.has_edge(other.id, node.id)
            ]
            if len(unexplained) >= 3:
                findings.append(
                    CodeSmell(
                        node_id=node.id,
                        smell_type="shotgun_surgery",
                        severity="medium",
                        description=(
                            f"{path} repeatedly changes with {len(unexplained)} unrelated files."
                        ),
                        suggestion=(
                            "Consolidate the scattered responsibility behind one module or API."
                        ),
                        evidence={"co_changes": unexplained},
                    )
                )

        # A node can participate in more than one cycle.  Preserve each complete
        # cycle but avoid exact duplicate findings from self-loops/parser overlap.
        unique: dict[tuple[str, str, str], CodeSmell] = {}
        for finding in findings:
            key = (finding.node_id, finding.smell_type, repr(finding.evidence))
            unique.setdefault(key, finding)
        ordered = sorted(
            unique.values(),
            key=lambda item: (item.smell_type, item.node_id, item.description),
        )
        if persist:
            self.store.save_findings(ordered)
        return ordered

    def _contained_descendants(self, node_id: str, scope: str) -> set[str]:
        graph = self.store.to_networkx(scope=scope, edge_types=(EdgeType.CONTAINS,))
        return set(nx.descendants(graph, node_id)) if node_id in graph else set()

    @staticmethod
    def _percentile_nearest_rank(values: Sequence[int], percentile: float) -> float:
        if not values:
            return 0.0
        position = (len(values) - 1) * percentile
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return float(values[lower])
        fraction = position - lower
        return float(values[lower] + (values[upper] - values[lower]) * fraction)

    def suggest_refactoring(self, node_id: str) -> list[dict[str, object]]:
        node = self.store.get_node(node_id)
        if node is None:
            raise ValueError(f"unknown graph node: {node_id}")
        graph = self.store.to_networkx(edge_types=IMPACT_EDGES)
        fan_in = graph.in_degree(node_id) if node_id in graph else 0
        fan_out = graph.out_degree(node_id) if node_id in graph else 0
        suggestions: list[dict[str, object]] = []
        if node.type is NodeType.CLASS and ((node.loc or 0) > 500 or node.method_count > 20):
            suggestions.append(
                {
                    "node_id": node.id,
                    "action": "extract_service",
                    "rationale": "The class has multiple size/responsibility signals.",
                    "confidence": 0.85,
                }
            )
        if fan_out > 10:
            suggestions.append(
                {
                    "node_id": node.id,
                    "action": "introduce_facade",
                    "rationale": f"Fan-out is {fan_out}; centralise outbound collaboration.",
                    "confidence": 0.75,
                }
            )
        if fan_in > 10 and fan_out > 5:
            suggestions.append(
                {
                    "node_id": node.id,
                    "action": "extract_interface",
                    "rationale": (
                        f"Fan-in {fan_in} and fan-out {fan_out} make changes ripple broadly."
                    ),
                    "confidence": 0.8,
                }
            )
        cycles = [cycle for cycle in self.detect_dependency_cycles() if node_id in cycle]
        if cycles:
            suggestions.append(
                {
                    "node_id": node.id,
                    "action": "invert_dependency",
                    "rationale": f"The node participates in {len(cycles)} dependency cycle(s).",
                    "confidence": 0.9,
                    "cycles": cycles,
                }
            )
        if node.type is NodeType.ROUTE and (node.complexity or 0) > 10:
            suggestions.append(
                {
                    "node_id": node.id,
                    "action": "extract_domain_handler",
                    "rationale": "Keep transport routing separate from complex domain logic.",
                    "confidence": 0.8,
                }
            )
        if not suggestions:
            suggestions.append(
                {
                    "node_id": node.id,
                    "action": "preserve_and_add_characterisation_tests",
                    "rationale": "No strong structural refactoring signal was detected.",
                    "confidence": 0.6,
                }
            )
        return sorted(
            suggestions,
            key=lambda item: (-float(str(item["confidence"])), str(item["action"])),
        )

    def impact_analysis(self, node_id_or_diff: str) -> ImpactResult:
        targets = self._impact_targets(node_id_or_diff)
        if not targets:
            return ImpactResult(
                target=node_id_or_diff,
                risk="low",
                rationale=["No indexed node matched the requested target."],
            )
        graph = self.store.to_networkx(edge_types=IMPACT_EDGES)
        node_map = {node.id: node for node in self.store.nodes()}
        direct: set[str] = set()
        transitive: set[str] = set()
        tests: set[str] = set()
        target_ids = {node.id for node in targets}
        for target_id in target_ids:
            if target_id not in graph:
                continue
            predecessors = set(graph.predecessors(target_id))
            for predecessor in predecessors:
                node = node_map.get(str(predecessor))
                if node and node.type is NodeType.TEST:
                    tests.add(node.id)
                elif predecessor not in target_ids:
                    direct.add(str(predecessor))
            for predecessor in nx.ancestors(graph, target_id):
                node = node_map.get(str(predecessor))
                if node and node.type is NodeType.TEST:
                    tests.add(node.id)
                elif predecessor not in target_ids and predecessor not in direct:
                    transitive.add(str(predecessor))

        # Include tests in the same file as an impacted production symbol and
        # explicitly connected TESTS edges that might not be on a shortest path.
        impacted_paths = {
            node_map[node_id].path
            for node_id in target_ids | direct | transitive
            if node_id in node_map
        }
        tests.update(
            node.id
            for node in node_map.values()
            if node.type is NodeType.TEST and node.path in impacted_paths
        )
        breadth = len(direct) + len(transitive)
        max_centrality = max((node.centrality or 0.0 for node in targets), default=0.0)
        if breadth >= 20 or len(direct) >= 8 or max_centrality >= 0.2:
            risk = "high"
        elif breadth >= 5 or len(direct) >= 2 or tests:
            risk = "medium"
        else:
            risk = "low"
        rationale = [
            f"{len(direct)} direct and {len(transitive)} transitive production dependents.",
            f"{len(tests)} related tests identified.",
        ]
        if max_centrality:
            rationale.append(f"Maximum target PageRank is {max_centrality:.4f}.")
        return ImpactResult(
            target=node_id_or_diff,
            direct_dependents=sorted(direct),
            transitive_dependents=sorted(transitive),
            related_tests=sorted(tests),
            risk=risk,
            rationale=rationale,
        )

    def _impact_targets(self, value: str) -> list[GraphNode]:
        direct = self.store.get_node(value)
        if direct:
            return [direct]
        paths = set(
            match.group(1).removeprefix("a/").removeprefix("b/")
            for match in re.finditer(r"(?m)^(?:\+\+\+|---)\s+([^\t\n]+)", value)
            if match.group(1) != "/dev/null"
        )
        if not paths and "\n" not in value:
            matches = self.store.find_nodes(value)
            files = [node for node in matches if node.type is NodeType.FILE]
            return files or matches
        targets: dict[str, GraphNode] = {}
        for path in sorted(paths):
            matches = self.store.find_nodes(path)
            file_matches = [
                node for node in matches if node.type is NodeType.FILE and node.path == path
            ]
            for node in file_matches or matches:
                targets[node.id] = node
        return list(targets.values())

    def parallel_impact_analysis(self, changes: Sequence[str]) -> list[ImpactResult]:
        # SQLite reads are cheap and deterministic ordering matters more than
        # threads here; this API is batch-parallel from the caller's perspective.
        return [self.impact_analysis(change) for change in changes]


def compute_centrality(store: GraphStore, scope: str = ".") -> dict[str, float]:
    return GraphAnalyzer(store).compute_centrality(scope)


def find_critical_files(store: GraphStore, top_n: int = 10) -> list[GraphNode]:
    return GraphAnalyzer(store).find_critical_files(top_n)


def detect_dependency_cycles(store: GraphStore) -> list[list[str]]:
    return GraphAnalyzer(store).detect_dependency_cycles()


def detect_code_smells(store: GraphStore, scope: str = ".") -> list[CodeSmell]:
    return GraphAnalyzer(store).detect_code_smells(scope)


def suggest_refactoring(store: GraphStore, node_id: str) -> list[dict[str, object]]:
    return GraphAnalyzer(store).suggest_refactoring(node_id)


def impact_analysis(store: GraphStore, node_id_or_diff: str) -> ImpactResult:
    return GraphAnalyzer(store).impact_analysis(node_id_or_diff)


def parallel_impact_analysis(store: GraphStore, changes: Sequence[str]) -> list[ImpactResult]:
    return GraphAnalyzer(store).parallel_impact_analysis(changes)


__all__ = [
    "DEPENDENCY_EDGES",
    "IMPACT_EDGES",
    "GraphAnalyzer",
    "compute_centrality",
    "detect_code_smells",
    "detect_dependency_cycles",
    "find_critical_files",
    "impact_analysis",
    "parallel_impact_analysis",
    "suggest_refactoring",
]
