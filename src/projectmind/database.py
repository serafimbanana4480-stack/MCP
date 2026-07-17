"""SQLite infrastructure and idempotent schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    root_path TEXT NOT NULL,
    index_revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    language TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    parse_status TEXT NOT NULL DEFAULT 'ok',
    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    start_line INTEGER,
    end_line INTEGER,
    language TEXT NOT NULL,
    complexity REAL,
    loc INTEGER,
    method_count INTEGER NOT NULL DEFAULT 0,
    centrality REAL,
    test_coverage REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path);
CREATE INDEX IF NOT EXISTS idx_nodes_qualname ON nodes(qualname);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_id TEXT REFERENCES nodes(id) ON DELETE CASCADE,
    target_ref TEXT,
    type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    evidence_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_id, target_id, target_ref, type)
);

CREATE INDEX IF NOT EXISTS idx_edges_source_type ON edges(source_id, type);
CREATE INDEX IF NOT EXISTS idx_edges_target_type ON edges(target_id, type);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    node_id TEXT REFERENCES nodes(id) ON DELETE SET NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_estimate INTEGER NOT NULL,
    summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);

CREATE TABLE IF NOT EXISTS analysis_findings (
    id TEXT PRIMARY KEY,
    node_id TEXT REFERENCES nodes(id) ON DELETE CASCADE,
    finding_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    suggestion TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    initial_confidence REAL NOT NULL CHECK (initial_confidence BETWEEN 0 AND 1),
    last_verified TEXT,
    created_at TEXT NOT NULL,
    branch TEXT,
    source TEXT NOT NULL,
    feedback_score REAL NOT NULL DEFAULT 0,
    superseded_by TEXT REFERENCES memories(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_memories_type_branch ON memories(type, branch, status);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY(memory_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags(tag);

CREATE TABLE IF NOT EXISTS memory_nodes (
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    PRIMARY KEY(memory_id, node_id)
);

CREATE TABLE IF NOT EXISTS embeddings (
    owner_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector BLOB NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY(owner_kind, owner_id, provider, model)
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    capability_mode TEXT NOT NULL DEFAULT 'deterministic',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thought_steps (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    success_criteria TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    evidence TEXT,
    UNIQUE(plan_id, step_number)
);

CREATE TABLE IF NOT EXISTS plan_tasks (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    parent_id TEXT,
    title TEXT NOT NULL,
    level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    checkpoints_json TEXT NOT NULL DEFAULT '[]',
    success_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_plan_tasks_plan ON plan_tasks(plan_id);

CREATE TABLE IF NOT EXISTS react_states (
    task_id TEXT PRIMARY KEY,
    iteration INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS long_tasks (
    id TEXT PRIMARY KEY,
    spec TEXT NOT NULL,
    plan_id TEXT REFERENCES plans(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active',
    checkpoints_json TEXT NOT NULL DEFAULT '[]',
    post_mortem_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    unified_diff TEXT NOT NULL,
    replacement_text TEXT,
    base_hash TEXT,
    proposal_digest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    applied_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_patches_status ON patches(status);

CREATE TABLE IF NOT EXISTS context_cache (
    cache_key TEXT PRIMARY KEY,
    index_revision INTEGER NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_events (
    id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    tokens_used INTEGER,
    success INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_telemetry_tool_time ON telemetry_events(tool_name, timestamp);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    success INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
"""


class Database:
    """Small SQLite facade with consistent safety pragmas and transactions."""

    def __init__(self, path: Path, project_root: Path) -> None:
        self.path = path
        self.project_root = project_root.resolve()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            connection.execute(
                """
                INSERT INTO project_state(singleton, root_path)
                VALUES (1, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    root_path = excluded.root_path,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(self.project_root),),
            )
            self._initialize_fts(connection)

    @staticmethod
    def _initialize_fts(connection: sqlite3.Connection) -> None:
        """Create FTS indexes when SQLite includes FTS5; search has a LIKE fallback."""

        try:
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(id UNINDEXED, content)"
            )
            connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts "
                "USING fts5(id UNINDEXED, content, summary)"
            )
        except sqlite3.OperationalError:
            # Some minimal SQLite builds omit FTS5. This is a documented graceful fallback.
            return

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def index_revision(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT index_revision FROM project_state WHERE singleton = 1"
            ).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def bump_index_revision(connection: sqlite3.Connection) -> int:
        connection.execute(
            """
            UPDATE project_state
            SET index_revision = index_revision + 1, updated_at = CURRENT_TIMESTAMP
            WHERE singleton = 1
            """
        )
        row = connection.execute(
            "SELECT index_revision FROM project_state WHERE singleton = 1"
        ).fetchone()
        return int(row[0])

