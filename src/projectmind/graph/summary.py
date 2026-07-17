"""Graph summary compatibility facade."""

from __future__ import annotations

from pathlib import Path

from projectmind.graph.store import GraphStore
from projectmind.models.graph_models import GraphSummary


def get_graph_summary(store: GraphStore, scope: str | Path = ".") -> GraphSummary:
    return store.summary(scope)


__all__ = ["get_graph_summary"]
