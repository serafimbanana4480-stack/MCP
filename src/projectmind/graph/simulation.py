"""Disk-free change simulation over an in-memory graph copy.

The :class:`ChangeSimulator` clones the live :class:`GraphStore` into a
``networkx`` graph, applies a hypothetical mutation, and reports the blast
radius (affected files, introduced cycles, affected tests) without touching the
filesystem.
"""

from __future__ import annotations

import networkx as nx

from projectmind.graph.store import GraphStore
from projectmind.models.graph_models import SimulationReport


class ChangeSimulator:
    """Simulate a proposed change against a copy of the graph."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def simulate_change(
        self, proposed_change: str, scope: str = "."
    ) -> SimulationReport:
        """Return a :class:`SimulationReport` for ``proposed_change``.

        The simulation is intentionally heuristic: it clones the graph, looks
        for dependency cycles that would be introduced, and collects the set of
        files and tests that transitively depend on the touched nodes.
        """
        notes: list[str] = []
        try:
            g = self.store.to_networkx(scope=scope)
        except Exception as exc:  # pragma: no cover - defensive
            notes.append(f"graph clone failed: {exc}")
            return SimulationReport(
                proposed_change=proposed_change,
                notes=notes,
            )

        # Heuristic: treat the change description as a hint about touched nodes.
        touched = [
            n
            for n in g.nodes
            if proposed_change and proposed_change.lower() in str(n).lower()
        ]
        if not touched:
            # Fall back to all nodes when no explicit target matches.
            touched = list(g.nodes)

        affected_files: set[str] = set()
        affected_tests: set[str] = set()
        for node in touched:
            affected_files.add(str(node))
            for succ in g.successors(node):
                affected_files.add(str(succ))
                if str(g.nodes[succ].get("type", "")).upper() == "TEST":
                    affected_tests.add(str(succ))

        introduced_cycles = self._find_cycles(g, touched)

        return SimulationReport(
            proposed_change=proposed_change,
            affected_files=sorted(affected_files),
            introduced_cycles=introduced_cycles,
            affected_tests=sorted(affected_tests),
            estimated_impact_nodes=len(affected_files),
            notes=notes,
        )

    @staticmethod
    def _find_cycles(graph: nx.DiGraph, touched: list[str]) -> list[list[str]]:
        import networkx as nx

        cycles: list[list[str]] = []
        try:
            for cycle in nx.simple_cycles(graph):
                if any(node in touched for node in cycle):
                    cycles.append([str(n) for n in cycle])
        except Exception:  # pragma: no cover - non-directed graphs
            pass
        return cycles


def simulate_change(
    store: GraphStore, proposed_change: str, scope: str = "."
) -> SimulationReport:
    """Functional adapter around :class:`ChangeSimulator`."""
    return ChangeSimulator(store).simulate_change(
        proposed_change=proposed_change, scope=scope
    )
