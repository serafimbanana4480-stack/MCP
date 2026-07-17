"""SQLite-backed CRUD, search, confidence ageing, and JSON portability."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from projectmind.config import MemoryConfig
from projectmind.database import Database
from projectmind.errors import ConflictError, NotFoundError, SecurityError
from projectmind.memory.branch_scoping import branch_is_visible, normalize_branch
from projectmind.models.common import new_id, utc_now
from projectmind.models.memory_models import (
    ConsolidationResult,
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
)

_WORD_RE = re.compile(r"[^\W_]+(?:[_'-][^\W_]+)*", re.UNICODE)
_EXPORT_SCHEMA_VERSION = 1
_MAX_IMPORT_BYTES = 50_000_000


def tokenize(value: str) -> list[str]:
    """Tokenize natural language and identifiers without external dependencies."""

    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value)
    return [match.group(0).casefold() for match in _WORD_RE.finditer(expanded)]


def effective_confidence(
    entry: MemoryEntry,
    *,
    now: datetime | None = None,
    half_life_days: float,
) -> float:
    """Calculate confidence with true half-life decay, without mutating history."""

    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    instant = now or utc_now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    anchor = entry.last_verified or entry.created_at
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    elapsed_days = max(0.0, (instant - anchor).total_seconds() / 86_400)
    decayed = entry.initial_confidence * math.pow(0.5, elapsed_days / half_life_days)
    return min(1.0, max(0.0, decayed))


class MemoryStore:
    """Persistent memory service with auditable, reversible mutations."""

    def __init__(
        self,
        database: Database,
        config: MemoryConfig | None = None,
        *,
        io_root: Path | None = None,
        current_branch: str | None = None,
        branch_resolver: Callable[[], str | None] | None = None,
    ) -> None:
        if current_branch is not None and branch_resolver is not None:
            raise ValueError("provide current_branch or branch_resolver, not both")
        self.database = database
        self.config = config or MemoryConfig()
        self.io_root = (io_root or database.project_root).resolve()
        self._configured_branch = normalize_branch(current_branch)
        self._branch_resolver = branch_resolver

    def create(
        self,
        content: str | MemoryEntry,
        *,
        memory_type: MemoryType | str = MemoryType.LESSON,
        summary: str | None = None,
        tags: Iterable[str] = (),
        related_node_ids: Iterable[str] = (),
        confidence: float | None = None,
        branch: str | None = None,
        source: str = "user",
        memory_id: str | None = None,
        created_at: datetime | None = None,
    ) -> MemoryEntry:
        """Create a memory or persist an already validated entry."""

        if isinstance(content, MemoryEntry):
            entry = self._canonical_entry(content)
        else:
            clean_content = content.strip()
            if not clean_content:
                raise ValueError("memory content cannot be empty")
            initial = self.config.default_confidence if confidence is None else confidence
            entry = MemoryEntry(
                id=memory_id or new_id("mem"),
                type=MemoryType(memory_type),
                content=clean_content,
                summary=summary.strip() if summary and summary.strip() else None,
                tags=self._normalize_values(tags),
                related_node_ids=self._normalize_values(related_node_ids),
                confidence=initial,
                initial_confidence=initial,
                created_at=created_at or utc_now(),
                branch=normalize_branch(
                    branch
                    if branch is not None
                    else (
                        self._resolve_current_branch()
                        if self.config.branch_scoped_by_default
                        else None
                    )
                ),
                source=source.strip() or "user",
            )
        self._validate_entry(entry)
        with self.database.transaction(immediate=True) as connection:
            self._insert(connection, entry)
            Database.bump_index_revision(connection)
        return entry

    # Familiar aliases make this service convenient for CLI and tool adapters.
    add = create
    record = create

    def record_decision(
        self,
        content: str,
        *,
        tags: Iterable[str] = (),
        related_node_ids: Iterable[str] = (),
        branch: str | None = None,
        confidence: float | None = None,
        source: str = "user",
    ) -> MemoryEntry:
        return self.create(
            content,
            memory_type=MemoryType.DECISION,
            tags=tags,
            related_node_ids=related_node_ids,
            branch=branch,
            confidence=confidence,
            source=source,
        )

    def record_learning(
        self,
        outcome: str,
        *,
        what_went_well: str = "",
        what_failed: str = "",
        lessons: str = "",
        tags: Iterable[str] = (),
        related_node_ids: Iterable[str] = (),
        branch: str | None = None,
        confidence: float | None = None,
        source: str = "user",
    ) -> MemoryEntry:
        sections = [("Outcome", outcome), ("Worked", what_went_well), ("Failed", what_failed)]
        sections.append(("Lessons", lessons))
        content = "\n".join(f"{label}: {text.strip()}" for label, text in sections if text.strip())
        return self.create(
            content,
            memory_type=MemoryType.LESSON,
            tags=tags,
            related_node_ids=related_node_ids,
            branch=branch,
            confidence=confidence,
            source=source,
        )

    def get(self, memory_id: str, *, include_deleted: bool = False) -> MemoryEntry:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row is None or (not include_deleted and row["status"] == "deleted"):
                raise NotFoundError(f"memory not found: {memory_id}")
            return self._entry_from_row(connection, row)

    get_memory = get

    def list_entries(
        self,
        *,
        memory_type: MemoryType | str | None = None,
        status: str | None = "active",
        limit: int | None = None,
    ) -> list[MemoryEntry]:
        clauses: list[str] = []
        parameters: list[object] = []
        if memory_type is not None:
            clauses.append("type = ?")
            parameters.append(MemoryType(memory_type).value)
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status)
        sql = "SELECT * FROM memories"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC, id ASC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            sql += " LIMIT ?"
            parameters.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
            return [self._entry_from_row(connection, row) for row in rows]

    list_memories = list_entries

    def update(self, memory_id: str, **changes: object) -> MemoryEntry:
        """Validate and replace mutable fields while preserving identity/history."""

        forbidden = {"id", "created_at"}
        unknown = set(changes) - set(MemoryEntry.model_fields)
        if unknown or forbidden.intersection(changes):
            invalid = sorted(unknown | forbidden.intersection(changes))
            raise ValueError(f"immutable or unknown memory fields: {', '.join(invalid)}")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"memory not found: {memory_id}")
            entry = self._entry_from_row(connection, row)
            normalized = dict(changes)
            if "tags" in normalized:
                normalized["tags"] = self._normalize_values(self._as_strings(normalized["tags"]))
            if "related_node_ids" in normalized:
                normalized["related_node_ids"] = self._normalize_values(
                    self._as_strings(normalized["related_node_ids"])
                )
            if "branch" in normalized:
                if normalized["branch"] is not None and not isinstance(
                    normalized["branch"], str
                ):
                    raise ValueError("branch must be a string or None")
                normalized["branch"] = normalize_branch(
                    normalized["branch"] if isinstance(normalized["branch"], str) else None
                )
            if "confidence" in normalized:
                normalized.setdefault("initial_confidence", normalized["confidence"])
                normalized.setdefault("last_verified", utc_now())
            updated = entry.model_copy(update=normalized)
            updated = MemoryEntry.model_validate(updated.model_dump())
            self._validate_entry(updated)
            self._replace(connection, updated)
            Database.bump_index_revision(connection)
        return updated

    update_memory = update

    def delete(self, memory_id: str, *, hard: bool = False) -> bool:
        """Soft-delete by default; hard deletion is explicit and still auditable by callers."""

        with self.database.transaction(immediate=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if exists is None:
                return False
            if hard:
                connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                self._delete_fts(connection, memory_id)
            else:
                connection.execute(
                    "UPDATE memories SET status = 'deleted' WHERE id = ?", (memory_id,)
                )
            Database.bump_index_revision(connection)
        return True

    delete_memory = delete

    def verify(self, memory_id: str, *, at: datetime | None = None) -> MemoryEntry:
        instant = at or utc_now()
        entry = self.get(memory_id, include_deleted=True)
        return self.update(
            memory_id,
            last_verified=instant,
            confidence=entry.initial_confidence,
        )

    verify_memory = verify

    def apply_feedback(
        self,
        memory_id: str,
        *,
        positive: bool,
        step: float = 0.1,
    ) -> MemoryEntry:
        if step <= 0 or step > 2:
            raise ValueError("feedback step must be in (0, 2]")
        entry = self.get(memory_id)
        delta = step if positive else -step
        score = min(1.0, max(-1.0, entry.feedback_score + delta))
        return self.update(memory_id, feedback_score=score)

    def feedback_thumbs_up(self, memory_id: str) -> MemoryEntry:
        return self.apply_feedback(memory_id, positive=True)

    def feedback_thumbs_down(self, memory_id: str) -> MemoryEntry:
        return self.apply_feedback(memory_id, positive=False)

    def feedback(
        self,
        memory_id: str,
        value: Literal["up", "down", 1, -1] | bool | None = None,
        *,
        positive: bool | None = None,
    ) -> MemoryEntry:
        """Record feedback through a compact service-friendly API."""

        if positive is not None:
            if value is not None:
                raise ValueError("provide value or positive, not both")
            direction = positive
        elif isinstance(value, bool):
            direction = value
        elif value in {"up", 1}:
            direction = True
        elif value in {"down", -1}:
            direction = False
        else:
            raise ValueError("feedback value must be up/down, 1/-1, or a boolean")
        return self.apply_feedback(memory_id, positive=direction)

    def aged_confidence(self, entry: MemoryEntry, *, now: datetime | None = None) -> float:
        half_life = (
            self.config.half_life_days_decision
            if entry.type in {MemoryType.DECISION, MemoryType.CONVENTION}
            else self.config.half_life_days_debug_note
        )
        return effective_confidence(entry, now=now, half_life_days=half_life)

    def search(
        self,
        query: str,
        *,
        memory_type: MemoryType | str | None = None,
        type: MemoryType | str | None = None,
        min_confidence: float = 0.0,
        branch: str | None = None,
        current_branch: str | None = None,
        include_global: bool = True,
        include_superseded: bool = False,
        include_deleted: bool = False,
        tags: Iterable[str] = (),
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[MemorySearchResult]:
        """Search content lexically, then apply branch, age, and feedback ranking."""

        if not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")
        if limit < 0:
            raise ValueError("limit cannot be negative")
        selected_type = memory_type if memory_type is not None else type
        if (
            memory_type is not None
            and type is not None
            and MemoryType(memory_type) != MemoryType(type)
        ):
            raise ValueError("memory_type and type disagree")
        entries = self.list_entries(memory_type=selected_type, status=None)
        requested_tags = set(self._normalize_values(tags))
        resolved_branch: str | None
        if current_branch is not None:
            resolved_branch = current_branch
        elif branch is not None:
            resolved_branch = branch
        elif self.config.branch_scoped_by_default:
            resolved_branch = self._resolve_current_branch()
        else:
            resolved_branch = None
        terms = list(dict.fromkeys(tokenize(query)))
        phrase = " ".join(terms)
        results: list[MemorySearchResult] = []
        for entry in entries:
            if not include_deleted and entry.status == "deleted":
                continue
            if not include_superseded and (entry.status == "superseded" or entry.superseded_by):
                continue
            if not branch_is_visible(
                entry.branch,
                resolved_branch,
                include_global=include_global,
            ):
                continue
            if requested_tags and not requested_tags.issubset(set(entry.tags)):
                continue
            confidence = self.aged_confidence(entry, now=now)
            if confidence < min_confidence:
                continue
            haystack = " ".join(
                part for part in (entry.content, entry.summary or "", " ".join(entry.tags)) if part
            )
            haystack_terms = set(tokenize(haystack))
            matched = [term for term in terms if term in haystack_terms]
            if terms and not matched:
                continue
            lexical = len(matched) / len(terms) if terms else 1.0
            normalized_haystack = " ".join(tokenize(haystack))
            if phrase and phrase in normalized_haystack:
                lexical = min(1.0, lexical * 0.85 + 0.15)
            feedback = (entry.feedback_score + 1.0) / 2.0
            score = min(1.0, max(0.0, 0.55 * lexical + 0.35 * confidence + 0.10 * feedback))
            visible = entry.model_copy(update={"confidence": confidence})
            results.append(
                MemorySearchResult(
                    entry=visible,
                    lexical_score=lexical,
                    effective_confidence=confidence,
                    score=score,
                    matched_terms=matched,
                )
            )
        results.sort(
            key=lambda result: (
                -result.score,
                -result.effective_confidence,
                -result.entry.created_at.timestamp(),
                result.entry.id,
            )
        )
        return results[:limit]

    memory_search = search

    def sources_for(self, memory_id: str) -> list[MemoryEntry]:
        """Return the direct source memories superseded by a consolidated entry."""

        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
            if exists is None:
                raise NotFoundError(f"memory not found: {memory_id}")
            rows = connection.execute(
                "SELECT * FROM memories WHERE superseded_by = ? ORDER BY id", (memory_id,)
            ).fetchall()
            return [self._entry_from_row(connection, row) for row in rows]

    def export_json(
        self,
        path: Path | str,
        *,
        allowed_root: Path | None = None,
        include_deleted: bool = False,
    ) -> Path:
        """Atomically export validated JSON below the service-authorized root."""

        target = self._safe_path(path, allowed_root=allowed_root, must_exist=False)
        entries = self.list_entries(status=None)
        if not include_deleted:
            entries = [entry for entry in entries if entry.status != "deleted"]
        payload = {
            "schema": "projectmind-memory",
            "schema_version": _EXPORT_SCHEMA_VERSION,
            "exported_at": utc_now().isoformat(),
            "memories": [entry.model_dump(mode="json") for entry in entries],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    export_memory = export_json

    def import_json(
        self,
        path: Path | str,
        *,
        allowed_root: Path | None = None,
        conflict: Literal["skip", "replace", "error"] = "skip",
    ) -> list[MemoryEntry]:
        """Validate an entire export before applying it in one transaction."""

        if conflict not in {"skip", "replace", "error"}:
            raise ValueError("conflict must be skip, replace, or error")
        source = self._safe_path(path, allowed_root=allowed_root, must_exist=True)
        if not source.is_file():
            raise SecurityError(f"memory import is not a regular file: {source}")
        if source.stat().st_size > _MAX_IMPORT_BYTES:
            raise SecurityError("memory import exceeds the 50 MB safety limit")
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid memory JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("memory import root must be an object")
        if raw.get("schema") != "projectmind-memory":
            raise ValueError("unsupported memory export schema")
        if raw.get("schema_version") != _EXPORT_SCHEMA_VERSION:
            raise ValueError(f"unsupported memory schema version: {raw.get('schema_version')!r}")
        values = raw.get("memories")
        if not isinstance(values, list):
            raise ValueError("memory export must contain a memories array")
        try:
            entries = [
                self._canonical_entry(MemoryEntry.model_validate(value)) for value in values
            ]
        except ValidationError as exc:
            raise ValueError(f"invalid memory entry: {exc}") from exc
        if len({entry.id for entry in entries}) != len(entries):
            raise ValueError("memory import contains duplicate ids")
        for entry in entries:
            self._validate_entry(entry)
        imported: list[MemoryEntry] = []
        with self.database.transaction(immediate=True) as connection:
            all_existing = {
                str(row[0]) for row in connection.execute("SELECT id FROM memories").fetchall()
            }
            existing = all_existing.intersection(entry.id for entry in entries)
            if existing and conflict == "error":
                raise ConflictError(f"memory ids already exist: {', '.join(sorted(existing))}")
            available_ids = all_existing | {entry.id for entry in entries}
            dangling = sorted(
                entry.id
                for entry in entries
                if entry.superseded_by is not None and entry.superseded_by not in available_ids
            )
            if dangling:
                raise ValueError(
                    "memory import contains dangling superseded_by references for: "
                    + ", ".join(dangling)
                )
            self._validate_import_cycles(entries)
            for entry in entries:
                if entry.id in existing and conflict == "skip":
                    continue
                staged = entry.model_copy(update={"superseded_by": None})
                if entry.id in existing:
                    self._replace(connection, staged)
                else:
                    self._insert(connection, staged)
                imported.append(entry)
            # Resolve forward references only after every imported id exists.
            for entry in imported:
                if entry.superseded_by is not None:
                    self._replace(connection, entry)
            if imported:
                Database.bump_index_revision(connection)
        return imported

    import_memory = import_json

    def consolidate(
        self,
        *,
        adapter: object | None = None,
        min_cluster_size: int | None = None,
        memory_type: MemoryType | str | None = None,
        branch: str | None = None,
    ) -> ConsolidationResult:
        """Consolidate through the optional adapter without coupling core storage to an LLM."""

        from projectmind.memory.consolidation import (
            ConsolidationAdapter,
            consolidate_memory,
        )

        if adapter is not None and not isinstance(adapter, ConsolidationAdapter):
            raise TypeError("adapter must implement consolidate(entries)")
        return consolidate_memory(
            self,
            adapter=adapter,
            min_cluster_size=min_cluster_size,
            memory_type=memory_type,
            branch=branch,
        )

    def _safe_path(
        self,
        path: Path | str,
        *,
        allowed_root: Path | None,
        must_exist: bool,
    ) -> Path:
        root = (allowed_root or self.io_root).resolve()
        candidate_path = Path(path)
        candidate = (
            candidate_path if candidate_path.is_absolute() else root / candidate_path
        ).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise SecurityError(f"path escapes authorized memory I/O root: {candidate}") from exc
        if candidate == root:
            raise SecurityError("memory I/O path must name a file below the authorized root")
        if must_exist and not candidate.exists():
            raise NotFoundError(f"memory import not found: {candidate}")
        return candidate

    def _resolve_current_branch(self) -> str | None:
        if self._branch_resolver is None:
            return self._configured_branch
        return normalize_branch(self._branch_resolver())

    @staticmethod
    def _normalize_values(values: Iterable[str]) -> list[str]:
        return sorted({clean for value in values if (clean := value.strip())})

    @classmethod
    def _canonical_entry(cls, entry: MemoryEntry) -> MemoryEntry:
        return entry.model_copy(
            deep=True,
            update={
                "content": entry.content.strip(),
                "summary": (
                    entry.summary.strip() if entry.summary and entry.summary.strip() else None
                ),
                "tags": cls._normalize_values(entry.tags),
                "related_node_ids": cls._normalize_values(entry.related_node_ids),
                "branch": normalize_branch(entry.branch),
                "source": entry.source.strip(),
            },
        )

    @staticmethod
    def _validate_import_cycles(entries: Iterable[MemoryEntry]) -> None:
        links = {
            entry.id: entry.superseded_by
            for entry in entries
            if entry.superseded_by is not None
        }
        for start in links:
            seen: set[str] = set()
            current: str | None = start
            while current in links:
                if current in seen:
                    raise ValueError("memory import contains a supersession cycle")
                seen.add(current)
                current = links[current]

    @staticmethod
    def _as_strings(value: object) -> Iterable[str]:
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise ValueError("expected an iterable of strings")
        values = list(value)
        if not all(isinstance(item, str) for item in values):
            raise ValueError("expected an iterable of strings")
        return values

    @staticmethod
    def _validate_entry(entry: MemoryEntry) -> None:
        if not entry.id.strip():
            raise ValueError("memory id cannot be empty")
        if len(entry.id) > 256 or any(ord(character) < 32 for character in entry.id):
            raise ValueError("memory id is too long or contains control characters")
        if not entry.content.strip():
            raise ValueError("memory content cannot be empty")
        if not entry.source.strip():
            raise ValueError("memory source cannot be empty")
        if not -1 <= entry.feedback_score <= 1:
            raise ValueError("feedback_score must be between -1 and 1")
        if entry.superseded_by == entry.id:
            raise ValueError("a memory cannot supersede itself")
        if entry.status not in {"active", "superseded", "deleted"}:
            raise ValueError("memory status must be active, superseded, or deleted")

    @staticmethod
    def _insert(connection: sqlite3.Connection, entry: MemoryEntry) -> None:
        try:
            connection.execute(
                """
                INSERT INTO memories(
                    id, type, content, summary, confidence, initial_confidence,
                    last_verified, created_at, branch, source, feedback_score,
                    superseded_by, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                MemoryStore._row_values(entry),
            )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"memory already exists or is invalid: {entry.id}") from exc
        MemoryStore._replace_relations(connection, entry)
        MemoryStore._upsert_fts(connection, entry)

    @staticmethod
    def _replace(connection: sqlite3.Connection, entry: MemoryEntry) -> None:
        cursor = connection.execute(
            """
            UPDATE memories SET
                type = ?, content = ?, summary = ?, confidence = ?, initial_confidence = ?,
                last_verified = ?, created_at = ?, branch = ?, source = ?, feedback_score = ?,
                superseded_by = ?, status = ?
            WHERE id = ?
            """,
            (
                entry.type.value,
                entry.content,
                entry.summary,
                entry.confidence,
                entry.initial_confidence,
                MemoryStore._datetime_value(entry.last_verified),
                MemoryStore._datetime_value(entry.created_at),
                entry.branch,
                entry.source,
                entry.feedback_score,
                entry.superseded_by,
                entry.status,
                entry.id,
            ),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"memory not found: {entry.id}")
        MemoryStore._replace_relations(connection, entry)
        MemoryStore._upsert_fts(connection, entry)

    @staticmethod
    def _replace_relations(connection: sqlite3.Connection, entry: MemoryEntry) -> None:
        connection.execute("DELETE FROM memory_tags WHERE memory_id = ?", (entry.id,))
        connection.execute("DELETE FROM memory_nodes WHERE memory_id = ?", (entry.id,))
        connection.executemany(
            "INSERT INTO memory_tags(memory_id, tag) VALUES (?, ?)",
            [(entry.id, tag) for tag in entry.tags],
        )
        connection.executemany(
            "INSERT INTO memory_nodes(memory_id, node_id) VALUES (?, ?)",
            [(entry.id, node_id) for node_id in entry.related_node_ids],
        )

    @staticmethod
    def _row_values(entry: MemoryEntry) -> tuple[object, ...]:
        return (
            entry.id,
            entry.type.value,
            entry.content,
            entry.summary,
            entry.confidence,
            entry.initial_confidence,
            MemoryStore._datetime_value(entry.last_verified),
            MemoryStore._datetime_value(entry.created_at),
            entry.branch,
            entry.source,
            entry.feedback_score,
            entry.superseded_by,
            entry.status,
        )

    @staticmethod
    def _datetime_value(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    @staticmethod
    def _entry_from_row(connection: sqlite3.Connection, row: Mapping[str, Any]) -> MemoryEntry:
        memory_id = str(row["id"])
        tags = [
            str(value[0])
            for value in connection.execute(
                "SELECT tag FROM memory_tags WHERE memory_id = ? ORDER BY tag", (memory_id,)
            ).fetchall()
        ]
        nodes = [
            str(value[0])
            for value in connection.execute(
                "SELECT node_id FROM memory_nodes WHERE memory_id = ? ORDER BY node_id",
                (memory_id,),
            ).fetchall()
        ]
        return MemoryEntry(
            id=memory_id,
            type=MemoryType(str(row["type"])),
            content=str(row["content"]),
            summary=str(row["summary"]) if row["summary"] is not None else None,
            tags=tags,
            related_node_ids=nodes,
            confidence=float(row["confidence"]),
            initial_confidence=float(row["initial_confidence"]),
            last_verified=row["last_verified"],
            created_at=row["created_at"],
            branch=str(row["branch"]) if row["branch"] is not None else None,
            source=str(row["source"]),
            feedback_score=float(row["feedback_score"]),
            superseded_by=(
                str(row["superseded_by"]) if row["superseded_by"] is not None else None
            ),
            status=str(row["status"]),
        )

    @staticmethod
    def _upsert_fts(connection: sqlite3.Connection, entry: MemoryEntry) -> None:
        try:
            connection.execute("DELETE FROM memories_fts WHERE id = ?", (entry.id,))
            connection.execute(
                "INSERT INTO memories_fts(id, content, summary) VALUES (?, ?, ?)",
                (entry.id, entry.content, entry.summary or ""),
            )
        except sqlite3.OperationalError:
            return

    @staticmethod
    def _delete_fts(connection: sqlite3.Connection, memory_id: str) -> None:
        try:
            connection.execute("DELETE FROM memories_fts WHERE id = ?", (memory_id,))
        except sqlite3.OperationalError:
            return
