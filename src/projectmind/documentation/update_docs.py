"""Generate documentation-update proposals from the live graph.

The :class:`DocsUpdater` inspects a :class:`GraphStore` and produces a
:class:`DocsUpdateProposal` containing :class:`DocPatch` objects. The tool never
writes to disk; the caller decides whether to apply the patches.
"""

from __future__ import annotations

from projectmind.graph.store import GraphStore
from projectmind.models.graph_models import GraphSummary
from projectmind.models.server_models import DocPatch, DocsUpdateProposal


class DocsUpdater:
    """Build documentation-update proposals from graph summaries."""

    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def update_docs(self, scope: str = ".", *, dry_run: bool = True) -> DocsUpdateProposal:
        summary = self.store.summary(scope=scope)
        patches: list[DocPatch] = [
            DocPatch(
                path="docs/architecture.md",
                section="auto-generated",
                content=self._architecture_snippet(scope, summary),
            ),
            DocPatch(
                path="docs/adr/0009-documentation-sync.md",
                section="auto-generated",
                content=self._adr_snippet(scope, summary),
            ),
            DocPatch(
                path="docs/api_reference.md",
                section="auto-generated",
                content=self._api_snippet(scope, summary),
            ),
        ]
        summary_text = (
            f"Scope '{scope}' contains {summary.files} files, {summary.nodes} nodes, "
            f"{summary.edges} edges across {len(summary.languages)} languages."
        )
        return DocsUpdateProposal(
            scope=scope, proposed_patches=patches, summary=summary_text
        )

    @staticmethod
    def _architecture_snippet(scope: str, summary: GraphSummary) -> str:
        lines = [f"## Architecture ({scope})", "", f"- Files: {summary.files}",
                 f"- Nodes: {summary.nodes}", f"- Edges: {summary.edges}", "",
                 "### Node types"]
        lines += [f"- {ntype}: {count}" for ntype, count in sorted(summary.node_types.items())]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _adr_snippet(scope: str, summary: GraphSummary) -> str:
        return (
            f"# ADR 0009: Documentation Sync ({scope})\n\n"
            f"Auto-generated proposal covering {summary.files} files and "
            f"{summary.nodes} graph nodes. Review before committing.\n"
        )

    @staticmethod
    def _api_snippet(scope: str, summary: GraphSummary) -> str:
        lines = [f"# API Reference ({scope})", "", "Generated from graph node types:"]
        lines += [f"- `{ntype}`: {count}" for ntype, count in sorted(summary.node_types.items())]
        return "\n".join(lines) + "\n"


def update_docs(
    store: GraphStore, scope: str = ".", *, dry_run: bool = True
) -> DocsUpdateProposal:
    """Functional adapter around :class:`DocsUpdater`."""
    return DocsUpdater(store).update_docs(scope=scope, dry_run=dry_run)
