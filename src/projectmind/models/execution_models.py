"""Patch, command, and security result models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PatchProposal(BaseModel):
    patch_id: str
    target: str
    unified_diff: str
    proposal_digest: str
    base_hash: str | None
    status: Literal["proposed", "applied", "expired", "rejected"] = "proposed"
    created_at: datetime
    expires_at: datetime
    warnings: list[str] = Field(default_factory=list)


class ApplyPatchResult(BaseModel):
    patch_id: str
    target: str
    applied: bool
    resulting_hash: str | None = None
    status: str


class CommandResult(BaseModel):
    argv: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False
    duration_ms: int


class SecurityFinding(BaseModel):
    rule_id: str
    severity: str
    path: str
    line: int | None = None
    description: str
    redacted_match: str | None = None

