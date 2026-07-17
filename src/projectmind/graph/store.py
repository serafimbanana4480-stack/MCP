"""SQLite persistence for the architectural graph."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import networkx as nx

from projectmind.database import Database
from projectmind.models.common import stable_id
from projectmind.models.graph_models import (
    CodeSmell,
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphSummary,
    NodeType,
)

if TYPE_CHECKING:
    from projectmind.indexing.extractor import ExtractionResult
    from projectmind.indexing.monorepo_detector import Workspace


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalise_path(path: str | Path) -> str:
    value = str(path).replace("\\", "/")
    normalised = PurePosixPath(value).as_posix()
    if normalised.startswith("./"):
        normalised = normalised[2:]
    normalised = normalised.lstrip("/")
    return normalised or "."


class GraphStore:
    """Typed facade over the graph tables created by :class:`Database`."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.root = database.project_root

    def sync_workspaces(
        self, workspaces: Iterable[Workspace], *, bump_revision: bool = True
    ) -> bool:
        ordered = sorted(workspaces, key=lambda item: (item.path, item.kind, item.id))
        desired = {
            item.id: (item.path, item.kind, item.name, _json(item.metadata)) for item in ordered
        }
        with self.database.transaction(immediate=True) as connection:
            existing = {
                str(row["id"]): (
                    str(row["path"]),
                    str(row["kind"]),
                    str(row["name"]),
                    str(row["metadata_json"]),
                )
                for row in connection.execute(
                    "SELECT id, path, kind, name, metadata_json FROM workspaces"
                )
            }
            if existing == desired:
                return False
            connection.execute("DELETE FROM workspaces")
            connection.executemany(
                """
                INSERT INTO workspaces(id, path, kind, name, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(workspace_id, *values) for workspace_id, values in desired.items()],
            )
            if bump_revision:
                Database.bump_index_revision(connection)
        return True

    def bump_revision(self) -> int:
        with self.database.transaction(immediate=True) as connection:
            return Database.bump_index_revision(connection)

    def list_workspaces(self) -> list[Workspace]:
        from projectmind.indexing.monorepo_detector import Workspace

        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, path, kind, name, metadata_json FROM workspaces ORDER BY path, kind, id"
            ).fetchall()
        return [
            Workspace(
                id=str(row["id"]),
                path=str(row["path"]),
                kind=str(row["kind"]),
                name=str(row["name"]),
                manifest=str(json.loads(row["metadata_json"] or "{}").get("manifest", "")),
                metadata=json.loads(row["metadata_json"] or "{}"),
            )
            for row in rows
        ]

    def upsert_workspace(self, workspace: Workspace) -> bool:
        desired = (
            workspace.id,
            workspace.path,
            workspace.kind,
            workspace.name,
            _json(workspace.metadata),
        )
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT id, path, kind, name, metadata_json
                FROM workspaces WHERE id = ? OR path = ?
                """,
                (workspace.id, workspace.path),
            ).fetchone()
            if row is not None and tuple(row) == desired:
                return False
            connection.execute(
                "DELETE FROM workspaces WHERE id = ? OR path = ?",
                (workspace.id, workspace.path),
            )
            connection.execute(
                """
                INSERT INTO workspaces(id, path, kind, name, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                desired,
            )
            Database.bump_index_revision(connection)
        return True

    def delete_workspace(self, workspace_id: str) -> bool:
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            if cursor.rowcount == 0:
                return False
            Database.bump_index_revision(connection)
        return True

    def file_hash(self, path: str | Path) -> str | None:
        relative = _normalise_path(path)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT content_hash FROM files WHERE path = ?", (relative,)
            ).fetchone()
        return str(row[0]) if row else None

    def file_paths(self, scope: str | Path = ".") -> list[str]:
        scope_value = self._validated_scope(scope)
        where, parameters = self._scope_clause(scope_value)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT path FROM files {where} ORDER BY path", parameters
            ).fetchall()
        return [str(row[0]) for row in rows]

    def list_files(self, scope: str | Path = ".") -> list[dict[str, object]]:
        scope_value = self._validated_scope(scope)
        where, parameters = self._scope_clause(scope_value)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM files {where} ORDER BY path", parameters
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_file(self, extraction: ExtractionResult, *, force: bool = False) -> bool:
        return bool(self.replace_files((extraction,), force=force))

    def replace_files(
        self,
        extractions: Iterable[ExtractionResult],
        *,
        remove_paths: Iterable[str | Path] = (),
        force: bool = False,
    ) -> list[str]:
        """Atomically replace a batch and increment the revision at most once."""

        by_path = {_normalise_path(item.path): item for item in extractions}
        requested_removals = {_normalise_path(path) for path in remove_paths} - set(by_path)
        changed: list[str] = []
        with self.database.transaction(immediate=True) as connection:
            existing_hashes = {
                str(row["path"]): str(row["content_hash"])
                for row in connection.execute("SELECT path, content_hash FROM files")
            }
            replacements = [
                item
                for path, item in sorted(by_path.items())
                if force or existing_hashes.get(path) != item.content_hash
            ]
            removals = sorted(path for path in requested_removals if path in existing_hashes)
            if not replacements and not removals:
                return []

            affected = sorted({_normalise_path(item.path) for item in replacements} | set(removals))
            self._detach_incoming(connection, affected)
            for path in affected:
                self._delete_file(connection, path)
            for path in removals:
                changed.append(path)
            for item in replacements:
                self._write_file_and_nodes(connection, item)
            for item in replacements:
                self._write_edges_and_chunks(connection, item)
                changed.append(_normalise_path(item.path))
            self._resolve_references(connection)
            Database.bump_index_revision(connection)
        return sorted(changed)

    def remove_file(self, path: str | Path) -> bool:
        return bool(self.replace_files((), remove_paths=(path,)))

    @staticmethod
    def _detach_incoming(connection: sqlite3.Connection, paths: Sequence[str]) -> None:
        if not paths:
            return
        placeholders = ",".join("?" for _ in paths)
        connection.execute(
            f"""
            UPDATE edges
            SET target_ref = COALESCE(
                    target_ref,
                    (SELECT qualname FROM nodes WHERE nodes.id = edges.target_id)
                ),
                target_id = NULL
            WHERE target_id IN (SELECT id FROM nodes WHERE path IN ({placeholders}))
              AND source_id NOT IN (SELECT id FROM nodes WHERE path IN ({placeholders}))
            """,
            (*paths, *paths),
        )

    @staticmethod
    def _delete_fts(connection: sqlite3.Connection, table: str, ids: Sequence[str]) -> None:
        if not ids:
            return
        with suppress(sqlite3.OperationalError):
            connection.executemany(f"DELETE FROM {table} WHERE id = ?", [(item,) for item in ids])

    def _delete_file(self, connection: sqlite3.Connection, path: str) -> None:
        chunk_ids = [
            str(row[0])
            for row in connection.execute("SELECT id FROM chunks WHERE path = ?", (path,))
        ]
        self._delete_fts(connection, "chunks_fts", chunk_ids)
        connection.execute("DELETE FROM files WHERE path = ?", (path,))

    def _write_file_and_nodes(
        self, connection: sqlite3.Connection, extraction: ExtractionResult
    ) -> None:
        path = _normalise_path(extraction.path)
        connection.execute(
            """
            INSERT INTO files(path, language, content_hash, mtime_ns, size_bytes, parse_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                path,
                extraction.language,
                extraction.content_hash,
                extraction.mtime_ns,
                extraction.size_bytes,
                extraction.parse_status,
            ),
        )
        connection.executemany(
            """
            INSERT INTO nodes(
                id, type, name, qualname, path, start_line, end_line, language,
                complexity, loc, method_count, centrality, test_coverage, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    node.id,
                    node.type.value,
                    node.name,
                    node.qualname,
                    path,
                    node.start_line,
                    node.end_line,
                    node.language,
                    node.complexity,
                    node.loc,
                    node.method_count,
                    node.centrality,
                    node.test_coverage,
                    _json(node.metadata),
                )
                for node in extraction.nodes
            ],
        )

    def _write_edges_and_chunks(
        self, connection: sqlite3.Connection, extraction: ExtractionResult
    ) -> None:
        path = _normalise_path(extraction.path)
        if any(edge.target_id is None and edge.target_ref is None for edge in extraction.edges):
            raise ValueError("every graph edge must have target_id or target_ref")
        connection.executemany(
            """
            INSERT INTO edges(
                source_id, target_id, target_ref, type, weight, confidence, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    edge.source_id,
                    edge.target_id,
                    edge.target_ref,
                    edge.type.value,
                    edge.weight,
                    edge.confidence,
                    _json(edge.evidence),
                )
                for edge in extraction.edges
            ],
        )
        connection.executemany(
            """
            INSERT INTO chunks(
                id, path, node_id, start_line, end_line, content, content_hash,
                token_estimate, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.id,
                    path,
                    chunk.node_id,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.content,
                    chunk.content_hash,
                    chunk.token_estimate,
                    chunk.summary,
                )
                for chunk in extraction.chunks
            ],
        )
        with suppress(sqlite3.OperationalError):
            connection.executemany(
                "INSERT INTO chunks_fts(id, content) VALUES (?, ?)",
                [(chunk.id, chunk.content) for chunk in extraction.chunks],
            )

    def resolve_references(self) -> int:
        with self.database.transaction(immediate=True) as connection:
            count = self._resolve_references(connection)
            if count:
                Database.bump_index_revision(connection)
        return count

    def _resolve_references(self, connection: sqlite3.Connection) -> int:
        nodes = connection.execute(
            "SELECT id, type, name, qualname, path, metadata_json FROM nodes ORDER BY id"
        ).fetchall()
        file_aliases: dict[str, list[str]] = {}
        symbol_aliases: dict[str, list[str]] = {}
        module_by_path: dict[str, str] = {}
        for row in nodes:
            node_id = str(row["id"])
            node_type = str(row["type"])
            name = str(row["name"])
            qualname = str(row["qualname"])
            path = str(row["path"])
            for alias in {name, qualname}:
                symbol_aliases.setdefault(alias, []).append(node_id)
            if node_type == NodeType.FILE.value:
                metadata = json.loads(row["metadata_json"] or "{}")
                module = str(metadata.get("module", ""))
                module_by_path[path] = module
                path_without_suffix = str(PurePosixPath(path).with_suffix(""))
                aliases = {
                    path,
                    path_without_suffix,
                    path_without_suffix.replace("/", "."),
                    module,
                    "./" + PurePosixPath(path_without_suffix).name,
                }
                if path.endswith("/__init__.py"):
                    aliases.add(path[: -len("/__init__.py")].replace("/", "."))
                for alias in filter(None, aliases):
                    file_aliases.setdefault(alias, []).append(node_id)

        updates: list[tuple[str, int]] = []
        unresolved = connection.execute(
            """
            SELECT edges.id, edges.target_ref, edges.type, source.path AS source_path
            FROM edges JOIN nodes AS source ON source.id = edges.source_id
            WHERE edges.target_id IS NULL AND edges.target_ref IS NOT NULL
            ORDER BY edges.id
            """
        ).fetchall()
        for row in unresolved:
            reference = str(row["target_ref"])
            edge_type = str(row["type"])
            source_path = str(row["source_path"])
            candidates: list[str]
            if edge_type == EdgeType.IMPORTS.value:
                import_aliases = self._import_aliases(reference, source_path, module_by_path)
                candidates = []
                for alias in import_aliases:
                    candidates.extend(file_aliases.get(alias, []))
                if not candidates:
                    # Go/Java absolute imports commonly end in the local module.
                    suffix_matches = [
                        ids[0]
                        for alias, ids in file_aliases.items()
                        if len(ids) == 1
                        and (reference.endswith(alias) or alias.endswith(reference))
                    ]
                    candidates.extend(suffix_matches)
            else:
                candidates = list(symbol_aliases.get(reference, []))
                if not candidates:
                    short = reference.rsplit(".", 1)[-1].rsplit("::", 1)[-1]
                    candidates = list(symbol_aliases.get(short, ()))
            unique = sorted(set(candidates))
            if len(unique) == 1:
                updates.append((unique[0], int(row["id"])))
        connection.executemany("UPDATE edges SET target_id = ? WHERE id = ?", updates)
        return len(updates)

    @staticmethod
    def _import_aliases(
        reference: str, source_path: str, module_by_path: Mapping[str, str]
    ) -> tuple[str, ...]:
        aliases = {reference, reference.removesuffix(".js"), reference.removesuffix(".ts")}
        source_directory = PurePosixPath(source_path).parent
        if reference.startswith("./") or reference.startswith("../"):
            joined = source_directory.joinpath(reference)
            # PurePath does not collapse '..'; use a small lexical normaliser.
            parts: list[str] = []
            for part in joined.parts:
                if part == ".." and parts:
                    parts.pop()
                elif part not in {".", ""}:
                    parts.append(part)
            local = "/".join(parts)
            aliases.update({local, local.replace("/", "."), f"{local}/index"})
        elif reference.startswith("."):
            level = len(reference) - len(reference.lstrip("."))
            tail = reference[level:].lstrip(".")
            source_module = module_by_path.get(source_path, "")
            package = source_module.split(".")[:-1]
            keep = max(0, len(package) - max(0, level - 1))
            resolved = ".".join((*package[:keep], *(part for part in tail.split(".") if part)))
            if resolved:
                aliases.add(resolved)
        return tuple(sorted(filter(None, aliases)))

    def get_node(self, node_id: str) -> GraphNode | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return self._row_to_node(row) if row else None

    def dependent_paths(
        self,
        paths: Iterable[str | Path],
        *,
        edge_types: Iterable[EdgeType | str] = (
            EdgeType.IMPORTS,
            EdgeType.CALLS,
            EdgeType.INHERITS,
            EdgeType.TESTS,
            EdgeType.ROUTES_TO,
            EdgeType.READS_WRITES_TABLE,
        ),
    ) -> list[str]:
        """Return paths with an incoming relationship to any node in ``paths``."""

        values = sorted({_normalise_path(path) for path in paths})
        types = sorted(
            item.value if isinstance(item, EdgeType) else str(item) for item in edge_types
        )
        if not values or not types:
            return []
        path_placeholders = ",".join("?" for _ in values)
        type_placeholders = ",".join("?" for _ in types)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT source.path
                FROM edges
                JOIN nodes AS source ON source.id = edges.source_id
                JOIN nodes AS target ON target.id = edges.target_id
                WHERE target.path IN ({path_placeholders})
                  AND source.path NOT IN ({path_placeholders})
                  AND edges.type IN ({type_placeholders})
                ORDER BY source.path
                """,
                (*values, *values, *types),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def find_nodes(
        self,
        reference: str,
        *,
        scope: str | Path = ".",
        node_types: Iterable[NodeType | str] | None = None,
    ) -> list[GraphNode]:
        nodes = self.nodes(scope=scope, node_types=node_types)
        exact = [
            node
            for node in nodes
            if node.id == reference or node.qualname == reference or node.name == reference
        ]
        if exact:
            return exact
        return [node for node in nodes if reference in node.qualname or reference in node.path]

    def nodes(
        self,
        *,
        scope: str | Path = ".",
        node_types: Iterable[NodeType | str] | None = None,
    ) -> list[GraphNode]:
        scope_value = self._validated_scope(scope)
        where, parameters = self._scope_clause(scope_value, column="path")
        values = tuple(
            item.value if isinstance(item, NodeType) else str(item) for item in node_types or ()
        )
        if values:
            prefix = "WHERE" if not where else "AND"
            placeholders = ",".join("?" for _ in values)
            where = f"{where} {prefix} type IN ({placeholders})"
            parameters = (*parameters, *values)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM nodes {where} ORDER BY id", parameters
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def edges(
        self,
        *,
        scope: str | Path = ".",
        edge_types: Iterable[EdgeType | str] | None = None,
    ) -> list[GraphEdge]:
        scope_value = self._validated_scope(scope)
        scope_where, parameters = self._scope_clause(scope_value, column="source.path")
        where = scope_where
        values = tuple(
            item.value if isinstance(item, EdgeType) else str(item) for item in edge_types or ()
        )
        if values:
            prefix = "WHERE" if not where else "AND"
            placeholders = ",".join("?" for _ in values)
            where = f"{where} {prefix} edges.type IN ({placeholders})"
            parameters = (*parameters, *values)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT edges.* FROM edges
                JOIN nodes AS source ON source.id = edges.source_id
                {where}
                ORDER BY source_id, type, COALESCE(target_id, ''),
                         COALESCE(target_ref, ''), edges.id
                """,
                parameters,
            ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def chunks(self, scope: str | Path = ".") -> list[dict[str, object]]:
        scope_value = self._validated_scope(scope)
        where, parameters = self._scope_clause(scope_value)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM chunks {where} ORDER BY path, start_line, id",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, scope: str | Path = ".") -> GraphSummary:
        scope_value = self._validated_scope(scope)
        file_where, file_params = self._scope_clause(scope_value, column="path")
        node_where, node_params = self._scope_clause(scope_value, column="path")
        edge_where, edge_params = self._scope_clause(scope_value, column="source.path")
        with self.database.connect() as connection:
            files = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM files {file_where}", file_params
                ).fetchone()[0]
            )
            nodes = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM nodes {node_where}", node_params
                ).fetchone()[0]
            )
            edges = int(
                connection.execute(
                    "SELECT COUNT(*) FROM edges "
                    "JOIN nodes source ON source.id=edges.source_id "
                    f"{edge_where}",
                    edge_params,
                ).fetchone()[0]
            )
            languages = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    f"SELECT language, COUNT(*) FROM files {file_where} "
                    "GROUP BY language ORDER BY language",
                    file_params,
                )
            }
            node_types = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    f"SELECT type, COUNT(*) FROM nodes {node_where} GROUP BY type ORDER BY type",
                    node_params,
                )
            }
        return GraphSummary(
            scope=scope_value,
            files=files,
            nodes=nodes,
            edges=edges,
            languages=languages,
            node_types=node_types,
            index_revision=self.database.index_revision(),
        )

    list_nodes = nodes
    list_edges = edges
    get_graph_summary = summary

    def to_networkx(
        self,
        *,
        scope: str | Path = ".",
        edge_types: Iterable[EdgeType | str] | None = None,
        include_unresolved: bool = False,
    ) -> nx.DiGraph:
        graph = nx.DiGraph()
        for node in self.nodes(scope=scope):
            graph.add_node(node.id, node=node, **node.model_dump(mode="json"))
        for edge in self.edges(scope=scope, edge_types=edge_types):
            target = edge.target_id
            if target is None and include_unresolved and edge.target_ref:
                target = f"unresolved:{edge.target_ref}"
                graph.add_node(target, unresolved=True, name=edge.target_ref)
            if target is None or target not in graph:
                continue
            graph.add_edge(
                edge.source_id,
                target,
                type=edge.type.value,
                weight=edge.weight,
                confidence=edge.confidence,
                edge=edge,
            )
        return graph

    def update_centrality(self, scores: Mapping[str, float]) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute("UPDATE nodes SET centrality = NULL")
            connection.executemany(
                "UPDATE nodes SET centrality = ? WHERE id = ?",
                [(float(score), node_id) for node_id, score in sorted(scores.items())],
            )

    def save_findings(self, findings: Iterable[CodeSmell]) -> None:
        ordered = sorted(findings, key=lambda item: (item.smell_type, item.node_id))
        with self.database.transaction(immediate=True) as connection:
            types = sorted(
                {item.smell_type for item in ordered}
                | {"god_class", "tight_coupling", "cyclic_dependency", "shotgun_surgery"}
            )
            if types:
                placeholders = ",".join("?" for _ in types)
                connection.execute(
                    f"DELETE FROM analysis_findings WHERE finding_type IN ({placeholders})", types
                )
            connection.executemany(
                """
                INSERT INTO analysis_findings(
                    id, node_id, finding_type, severity, description, suggestion, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        stable_id("finding", item.smell_type, item.node_id, _json(item.evidence)),
                        item.node_id,
                        item.smell_type,
                        item.severity,
                        item.description,
                        item.suggestion,
                        _json(item.evidence),
                    )
                    for item in ordered
                ],
            )

    def _validated_scope(self, scope: str | Path) -> str:
        candidate = Path(scope)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.root / candidate).resolve()
        try:
            relative = resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise ValueError(f"scope is outside project root: {scope}") from exc
        return "." if relative == "." else relative.rstrip("/")

    @staticmethod
    def _scope_clause(scope: str, *, column: str = "path") -> tuple[str, tuple[str, ...]]:
        if scope == ".":
            return "", ()
        return f"WHERE ({column} = ? OR {column} LIKE ?)", (scope, f"{scope}/%")

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            id=str(row["id"]),
            type=NodeType(str(row["type"])),
            name=str(row["name"]),
            qualname=str(row["qualname"]),
            path=str(row["path"]),
            start_line=row["start_line"],
            end_line=row["end_line"],
            language=str(row["language"]),
            complexity=row["complexity"],
            loc=row["loc"],
            method_count=int(row["method_count"]),
            centrality=row["centrality"],
            test_coverage=row["test_coverage"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> GraphEdge:
        return GraphEdge(
            source_id=str(row["source_id"]),
            target_id=str(row["target_id"]) if row["target_id"] is not None else None,
            target_ref=str(row["target_ref"]) if row["target_ref"] is not None else None,
            type=EdgeType(str(row["type"])),
            weight=float(row["weight"]),
            confidence=float(row["confidence"]),
            evidence=json.loads(row["evidence_json"] or "{}"),
        )


__all__ = ["GraphStore"]
