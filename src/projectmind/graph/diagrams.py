"""Deterministic text diagram exporters."""

from __future__ import annotations

import re
from typing import Literal

from projectmind.graph.store import GraphStore

DiagramFormat = Literal["mermaid", "plantuml", "dot"]


def _alias(node_id: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", node_id)


def _display_label(name: str, node_type: str, path: str) -> str:
    return f"{name}\n[{node_type}]\n{path}"


def _mermaid_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("\r", "")
        .replace("\n", "<br/>")
    )


def _quoted_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "\\n")


class DiagramExporter:
    def __init__(self, store: GraphStore) -> None:
        self.store = store

    def export(self, scope: str = ".", format: DiagramFormat | str = "mermaid") -> str:
        selected = format.lower()
        if selected == "mermaid":
            return self.to_mermaid(scope)
        if selected == "plantuml":
            return self.to_plantuml(scope)
        if selected == "dot":
            return self.to_dot(scope)
        raise ValueError(f"unsupported diagram format: {format}")

    export_diagram = export

    def to_mermaid(self, scope: str = ".") -> str:
        graph = self.store.to_networkx(scope=scope)
        lines = ["flowchart LR"]
        if not graph.nodes:
            lines.append("  %% empty graph")
            return "\n".join(lines)
        for node_id, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
            label = _display_label(
                str(data.get("name", node_id)),
                str(data.get("type", "unknown")),
                str(data.get("path", "")),
            )
            lines.append(f'  {_alias(str(node_id))}["{_mermaid_escape(label)}"]')
        for source, target, data in sorted(
            graph.edges(data=True),
            key=lambda item: (
                str(item[0]),
                str(item[1]),
                str(item[2].get("type", "")),
            ),
        ):
            edge_type = _mermaid_escape(str(data.get("type", "related")))
            lines.append(f"  {_alias(str(source))} -->|{edge_type}| {_alias(str(target))}")
        return "\n".join(lines)

    def to_plantuml(self, scope: str = ".") -> str:
        graph = self.store.to_networkx(scope=scope)
        lines = ["@startuml", "left to right direction", "skinparam componentStyle rectangle"]
        for node_id, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
            label = _quoted_escape(
                _display_label(
                    str(data.get("name", node_id)),
                    str(data.get("type", "unknown")),
                    str(data.get("path", "")),
                )
            )
            lines.append(f'component "{label}" as {_alias(str(node_id))}')
        for source, target, data in sorted(
            graph.edges(data=True),
            key=lambda item: (
                str(item[0]),
                str(item[1]),
                str(item[2].get("type", "")),
            ),
        ):
            label = _quoted_escape(str(data.get("type", "related")))
            lines.append(f"{_alias(str(source))} --> {_alias(str(target))} : {label}")
        lines.append("@enduml")
        return "\n".join(lines)

    def to_dot(self, scope: str = ".") -> str:
        graph = self.store.to_networkx(scope=scope)
        lines = ["digraph ProjectMind {", "  rankdir=LR;"]
        for node_id, data in sorted(graph.nodes(data=True), key=lambda item: str(item[0])):
            label = _quoted_escape(
                _display_label(
                    str(data.get("name", node_id)),
                    str(data.get("type", "unknown")),
                    str(data.get("path", "")),
                )
            )
            lines.append(f'  {_alias(str(node_id))} [label="{label}"];')
        for source, target, data in sorted(
            graph.edges(data=True),
            key=lambda item: (
                str(item[0]),
                str(item[1]),
                str(item[2].get("type", "")),
            ),
        ):
            label = _quoted_escape(str(data.get("type", "related")))
            lines.append(f'  {_alias(str(source))} -> {_alias(str(target))} [label="{label}"];')
        lines.append("}")
        return "\n".join(lines)


def export_diagram(
    store: GraphStore, scope: str = ".", format: DiagramFormat | str = "mermaid"
) -> str:
    return DiagramExporter(store).export(scope, format)


__all__ = ["DiagramExporter", "DiagramFormat", "export_diagram"]
