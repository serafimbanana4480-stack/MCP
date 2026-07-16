from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, language TEXT, framework TEXT, hash TEXT NOT NULL, size_bytes INTEGER NOT NULL, last_indexed_at TEXT NOT NULL, git_last_commit TEXT, is_test INTEGER NOT NULL DEFAULT 0, content TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS symbols (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL, name TEXT NOT NULL, qualified_name TEXT NOT NULL, kind TEXT NOT NULL, start_line INTEGER, end_line INTEGER, signature TEXT, docstring TEXT, complexity INTEGER, FOREIGN KEY(file_id) REFERENCES files(id));
CREATE TABLE IF NOT EXISTS edges (id INTEGER PRIMARY KEY, source_type TEXT NOT NULL, source_id INTEGER NOT NULL, target_type TEXT NOT NULL, target_id INTEGER NOT NULL, relation TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0, evidence TEXT);
CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, confidence REAL NOT NULL, provenance TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', branch TEXT, last_verified_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(type,title,branch));
CREATE TABLE IF NOT EXISTS memory_feedback (id INTEGER PRIMARY KEY, context_ref TEXT NOT NULL, signal TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS branches (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, base_commit TEXT, metadata TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS task_cache (task_hash TEXT PRIMARY KEY, task TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scoring_weights (name TEXT PRIMARY KEY, value REAL NOT NULL);
CREATE TABLE IF NOT EXISTS telemetry (id INTEGER PRIMARY KEY, event_id TEXT UNIQUE, action TEXT NOT NULL, ref TEXT, justification TEXT, status TEXT, payload TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage_ledger (event_id TEXT PRIMARY KEY, action TEXT NOT NULL, model TEXT NOT NULL DEFAULT 'local', input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0, cached_tokens INTEGER NOT NULL DEFAULT 0, cache_hit INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0, ref TEXT, payload TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_links (memory_id INTEGER NOT NULL, ref_type TEXT NOT NULL, ref_id TEXT NOT NULL, UNIQUE(memory_id,ref_type,ref_id));
CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, objective TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS debug_sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reasoning_sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alternatives (id TEXT PRIMARY KEY, session_id TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS critiques (id TEXT PRIMARY KEY, ref TEXT NOT NULL, data TEXT NOT NULL, verdict TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS learnings (id TEXT PRIMARY KEY, task_ref TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS risk_matrix (id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(path, content);
CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts USING fts5(name, qualified_name, signature, docstring);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(title, body);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, tuple(params))
        self.conn.commit()
        return cur

    def rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        row = self.conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None

    def put_json(
        self, table: str, key: str, key_value: str, data: dict[str, Any], status: str = "active"
    ) -> None:
        self.execute(
            f"INSERT INTO {table}(id,data,status,updated_at) VALUES(?,?,?,datetime('now')) ON CONFLICT(id) DO UPDATE SET data=excluded.data,status=excluded.status,updated_at=excluded.updated_at",
            (key_value, json.dumps(data, default=str), status),
        )
