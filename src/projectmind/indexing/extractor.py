"""Convert parser records into canonical graph models."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from projectmind.indexing.discovery import DiscoveredFile, detect_language
from projectmind.indexing.parsers import ParseResult, ParserRegistry
from projectmind.models.common import stable_id
from projectmind.models.graph_models import EdgeType, GraphEdge, GraphNode, NodeType


@dataclass(frozen=True, slots=True)
class ExtractedChunk:
    id: str
    path: str
    node_id: str | None
    start_line: int
    end_line: int
    content: str
    content_hash: str
    token_estimate: int
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    path: str
    language: str
    content_hash: str
    mtime_ns: int
    size_bytes: int
    parse_status: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    chunks: tuple[ExtractedChunk, ...]
    warnings: tuple[str, ...] = ()

    @property
    def file_node(self) -> GraphNode:
        return next(node for node in self.nodes if node.type is NodeType.FILE)


def module_name_for_path(relative_path: str) -> str:
    path = PurePosixPath(relative_path)
    stem_parts = list(path.with_suffix("").parts)
    if stem_parts and stem_parts[-1] in {"__init__", "index", "mod"}:
        stem_parts.pop()
    return ".".join(stem_parts) or path.stem


def _node_id(relative_path: str, qualname: str) -> str:
    return stable_id("node", relative_path, qualname)


class Extractor:
    """Read a source file and emit stable graph objects."""

    def __init__(self, root: Path | str, registry: ParserRegistry | None = None) -> None:
        self.root = Path(root).resolve()
        self.registry = registry or ParserRegistry()

    def extract(self, file: DiscoveredFile | Path | str) -> ExtractionResult:
        discovered = self._coerce_file(file)
        try:
            raw = discovered.path.read_bytes()
        except OSError as exc:
            return self._failed_result(discovered, b"", f"cannot read source: {exc}")
        if b"\x00" in raw:
            return self._failed_result(discovered, raw, "binary content skipped")
        source = raw.decode("utf-8", errors="replace")
        parsed = self.registry.parse(source, discovered.path, discovered.language)
        return self._build(discovered, raw, source, parsed)

    def extract_source(
        self,
        source: str,
        relative_path: str,
        *,
        language: str | None = None,
        mtime_ns: int = 0,
    ) -> ExtractionResult:
        """Extract in-memory source; useful for editors and unit tests."""

        clean_path = PurePosixPath(relative_path.replace("\\", "/")).as_posix().lstrip("/")
        selected_language = language or detect_language(clean_path)
        if selected_language is None:
            raise ValueError(f"unsupported source extension: {relative_path}")
        raw = source.encode("utf-8")
        discovered = DiscoveredFile(
            path=self.root / Path(clean_path),
            relative_path=clean_path,
            language=selected_language,
            size_bytes=len(raw),
            mtime_ns=mtime_ns,
        )
        parsed = self.registry.parse(source, clean_path, selected_language)
        return self._build(discovered, raw, source, parsed)

    def _coerce_file(self, file: DiscoveredFile | Path | str) -> DiscoveredFile:
        if isinstance(file, DiscoveredFile):
            return file
        path = Path(file)
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        try:
            relative = path.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError(f"source is outside project root: {path}") from exc
        language = detect_language(path)
        if language is None:
            raise ValueError(f"unsupported source extension: {path.suffix}")
        stat = path.stat()
        return DiscoveredFile(path, relative, language, stat.st_size, stat.st_mtime_ns)

    def _failed_result(
        self, discovered: DiscoveredFile, raw: bytes, warning: str
    ) -> ExtractionResult:
        file_node, module_node, contains = self._base_nodes(discovered, 0, "unavailable")
        return ExtractionResult(
            path=discovered.relative_path,
            language=discovered.language,
            content_hash=hashlib.sha256(raw).hexdigest(),
            mtime_ns=discovered.mtime_ns,
            size_bytes=discovered.size_bytes,
            parse_status="error",
            nodes=(file_node, module_node),
            edges=(contains,),
            chunks=(),
            warnings=(warning,),
        )

    def _base_nodes(
        self, discovered: DiscoveredFile, line_count: int, adapter: str
    ) -> tuple[GraphNode, GraphNode, GraphEdge]:
        relative = discovered.relative_path
        module_name = module_name_for_path(relative)
        file_id = _node_id(relative, relative)
        module_id = _node_id(relative, module_name)
        file_node = GraphNode(
            id=file_id,
            type=NodeType.FILE,
            name=PurePosixPath(relative).name,
            qualname=relative,
            path=relative,
            start_line=1 if line_count else None,
            end_line=line_count or None,
            language=discovered.language,
            loc=line_count,
            metadata={"module": module_name, "parser": adapter},
        )
        module_node = GraphNode(
            id=module_id,
            type=NodeType.MODULE,
            name=module_name.rsplit(".", 1)[-1],
            qualname=module_name,
            path=relative,
            start_line=1 if line_count else None,
            end_line=line_count or None,
            language=discovered.language,
            loc=line_count,
            metadata={"parser": adapter},
        )
        contains = GraphEdge(
            source_id=file_id,
            target_id=module_id,
            type=EdgeType.CONTAINS,
            evidence={"kind": "file_module"},
        )
        return file_node, module_node, contains

    def _build(
        self,
        discovered: DiscoveredFile,
        raw: bytes,
        source: str,
        parsed: ParseResult,
    ) -> ExtractionResult:
        relative = discovered.relative_path
        lines = source.splitlines()
        file_node, module_node, base_edge = self._base_nodes(discovered, len(lines), parsed.adapter)
        nodes: list[GraphNode] = [file_node, module_node]
        edges: list[GraphEdge] = [base_edge]
        by_qualname: dict[str, str] = {module_node.qualname: module_node.id}

        kind_map = {
            "class": NodeType.CLASS,
            "function": NodeType.FUNCTION,
            "method": NodeType.METHOD,
            "test": NodeType.TEST,
        }
        for symbol in sorted(
            parsed.symbols,
            key=lambda item: (item.start_line, item.qualname, item.kind),
        ):
            node_type = kind_map.get(symbol.kind)
            if node_type is None:
                continue
            node_id = _node_id(relative, symbol.qualname)
            metadata = dict(symbol.metadata)
            metadata.update({"parser": parsed.adapter, "confidence": parsed.confidence})
            node = GraphNode(
                id=node_id,
                type=node_type,
                name=symbol.name,
                qualname=symbol.qualname,
                path=relative,
                start_line=max(1, symbol.start_line),
                end_line=max(symbol.start_line, symbol.end_line),
                language=discovered.language,
                complexity=symbol.complexity,
                loc=symbol.loc,
                method_count=symbol.method_count,
                metadata=metadata,
            )
            nodes.append(node)
            by_qualname[symbol.qualname] = node_id

        # Containment is resolved after all symbols exist, including containers
        # declared later by a fallback parser.
        for symbol in parsed.symbols:
            child_id = by_qualname.get(symbol.qualname)
            if child_id is None:
                continue
            parent_id = by_qualname.get(symbol.container or "", module_node.id)
            edges.append(
                GraphEdge(
                    source_id=parent_id,
                    target_id=child_id,
                    type=EdgeType.CONTAINS,
                    confidence=parsed.confidence,
                    evidence={"parser": parsed.adapter},
                )
            )

        for imported in parsed.imports:
            reference = ("." * imported.relative_level) + imported.module
            if imported.relative_level and not imported.module and imported.names:
                reference += imported.names[0]
            elif not reference and imported.names:
                reference = imported.names[0]
            if not reference:
                continue
            edges.append(
                GraphEdge(
                    source_id=file_node.id,
                    target_ref=reference,
                    type=EdgeType.IMPORTS,
                    confidence=parsed.confidence,
                    evidence={
                        "line": imported.line,
                        "names": list(imported.names),
                        "parser": parsed.adapter,
                    },
                )
            )

        for relation in parsed.relations:
            source_id = by_qualname.get(relation.source_qualname or "", module_node.id)
            target_id = self._local_target(by_qualname, relation.target_ref)
            edge_type = {
                "calls": EdgeType.CALLS,
                "inherits": EdgeType.INHERITS,
                "tests": EdgeType.TESTS,
            }.get(relation.relation)
            if edge_type is None:
                continue
            edges.append(
                GraphEdge(
                    source_id=source_id,
                    target_id=target_id,
                    target_ref=None if target_id else relation.target_ref,
                    type=edge_type,
                    confidence=min(parsed.confidence, relation.confidence),
                    evidence={"line": relation.line, "parser": parsed.adapter, **relation.metadata},
                )
            )

        for route in parsed.routes:
            handler_reference = route.handler_qualname or "anonymous"
            route_qualname = f"route:{route.method}:{route.route_path}->{handler_reference}"
            route_id = _node_id(relative, route_qualname)
            route_node = GraphNode(
                id=route_id,
                type=NodeType.ROUTE,
                name=f"{route.method} {route.route_path}",
                qualname=route_qualname,
                path=relative,
                start_line=route.line,
                end_line=route.line,
                language=discovered.language,
                loc=1,
                metadata={
                    "method": route.method,
                    "route": route.route_path,
                    "framework": route.framework,
                },
            )
            nodes.append(route_node)
            edges.append(
                GraphEdge(
                    source_id=module_node.id,
                    target_id=route_id,
                    type=EdgeType.CONTAINS,
                )
            )
            handler_id = self._local_target(by_qualname, route.handler_qualname or "")
            if handler_id or route.handler_qualname:
                edges.append(
                    GraphEdge(
                        source_id=route_id,
                        target_id=handler_id,
                        target_ref=None if handler_id else route.handler_qualname,
                        type=EdgeType.ROUTES_TO,
                        confidence=parsed.confidence,
                        evidence={"line": route.line, "framework": route.framework},
                    )
                )

        seen_tables: dict[str, str] = {}
        for table in sorted(parsed.tables, key=lambda item: (item.name, item.line, item.orm)):
            table_key = table.name.lower()
            table_id = seen_tables.get(table_key)
            if table_id is None:
                table_qualname = f"table:{table.name}"
                table_id = _node_id(relative, table_qualname)
                seen_tables[table_key] = table_id
                nodes.append(
                    GraphNode(
                        id=table_id,
                        type=NodeType.DB_TABLE,
                        name=table.name,
                        qualname=table_qualname,
                        path=relative,
                        start_line=table.line,
                        end_line=table.line,
                        language=discovered.language,
                        loc=1,
                        metadata={"orm": table.orm},
                    )
                )
                edges.append(
                    GraphEdge(source_id=module_node.id, target_id=table_id, type=EdgeType.CONTAINS)
                )
            owner_id = self._local_target(by_qualname, table.owner_qualname or "") or module_node.id
            edges.append(
                GraphEdge(
                    source_id=owner_id,
                    target_id=table_id,
                    type=EdgeType.READS_WRITES_TABLE,
                    confidence=parsed.confidence,
                    evidence={"line": table.line, "orm": table.orm, "access": table.access},
                )
            )

        # Exact duplicate edges can arise when a parser sees the same ORM access
        # more than once.  Keep one stable representation before persistence.
        edge_map: dict[tuple[str, str | None, str | None, str], GraphEdge] = {}
        for edge in edges:
            key = (edge.source_id, edge.target_id, edge.target_ref, edge.type.value)
            edge_map.setdefault(key, edge)
        node_map = {node.id: node for node in nodes}
        chunks = self._chunks(relative, lines, node_map.values())
        status = "ok" if not parsed.errors else "partial"
        return ExtractionResult(
            path=relative,
            language=discovered.language,
            content_hash=hashlib.sha256(raw).hexdigest(),
            mtime_ns=discovered.mtime_ns,
            size_bytes=discovered.size_bytes,
            parse_status=status,
            nodes=tuple(sorted(node_map.values(), key=lambda item: item.id)),
            edges=tuple(
                sorted(
                    edge_map.values(),
                    key=lambda item: (
                        item.source_id,
                        item.type.value,
                        item.target_id or "",
                        item.target_ref or "",
                    ),
                )
            ),
            chunks=chunks,
            warnings=parsed.errors,
        )

    @staticmethod
    def _local_target(by_qualname: dict[str, str], reference: str) -> str | None:
        if reference in by_qualname:
            return by_qualname[reference]
        candidates = [
            node_id
            for qualname, node_id in by_qualname.items()
            if qualname.rsplit(".", 1)[-1] == reference.rsplit(".", 1)[-1]
        ]
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _chunks(
        relative: str,
        lines: list[str],
        nodes: Iterable[GraphNode],
    ) -> tuple[ExtractedChunk, ...]:
        chunks: list[ExtractedChunk] = []
        for node in nodes:
            if node.type in {NodeType.FILE, NodeType.MODULE}:
                continue
            if (
                node.start_line is None
                or node.end_line is None
                or node.type in {NodeType.ROUTE, NodeType.DB_TABLE}
            ):
                continue
            content = "\n".join(lines[node.start_line - 1 : node.end_line])
            if not content:
                continue
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            chunks.append(
                ExtractedChunk(
                    id=stable_id("chunk", relative, node.id, digest),
                    path=relative,
                    node_id=node.id,
                    start_line=node.start_line,
                    end_line=node.end_line,
                    content=content,
                    content_hash=digest,
                    token_estimate=max(1, (len(content) + 3) // 4),
                    summary=f"{node.type.value} {node.qualname}",
                )
            )
        return tuple(sorted(chunks, key=lambda item: (item.start_line, item.id)))


CodeExtractor = Extractor


def extract_file(path: Path | str, root: Path | str | None = None) -> ExtractionResult:
    source_path = Path(path)
    selected_root = Path(root).resolve() if root is not None else source_path.resolve().parent
    return Extractor(selected_root).extract(source_path)


__all__ = [
    "CodeExtractor",
    "ExtractedChunk",
    "ExtractionResult",
    "Extractor",
    "extract_file",
    "module_name_for_path",
]
