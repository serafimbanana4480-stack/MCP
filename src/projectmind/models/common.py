"""Shared response envelopes, provenance, and identifier helpers."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8", errors="surrogatepass")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


class Provenance(BaseModel):
    """A verifiable source contributing to a result."""

    kind: str
    reference: str
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    content_hash: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class ToolErrorInfo(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] = Field(default_factory=dict)


class ToolMeta(BaseModel):
    request_id: str = Field(default_factory=lambda: new_id("req"))
    index_revision: int = 0
    capability_mode: Literal["deterministic", "llm_enhanced"] = "deterministic"
    duration_ms: int = 0


class ToolResult(BaseModel, Generic[T]):
    """Uniform structured output for MCP and CLI use cases."""

    ok: bool
    data: T | None = None
    error: ToolErrorInfo | None = None
    provenance: list[Provenance] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: ToolMeta = Field(default_factory=ToolMeta)


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"
    name: str = "projectmind"
    version: str
    protocol_transport: str | None = None
    project_root: str
    database_ready: bool

