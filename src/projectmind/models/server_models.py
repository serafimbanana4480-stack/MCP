"""MCP server discovery and operational status models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CapabilitiesResult(BaseModel):
    server: str = "projectmind"
    version: str
    mcp_specification: str = "2025-11-25"
    transports: list[str] = Field(default_factory=lambda: ["stdio", "streamable-http"])
    capability_mode: str
    features: dict[str, str] = Field(default_factory=dict)
    tool_profile: str


class ProjectStatus(BaseModel):
    project_root: str
    initialized: bool
    database_path: str
    index_revision: int
    workspaces: int = 0
    files: int = 0
    nodes: int = 0
    edges: int = 0
    memories: int = 0
    plans: int = 0
    proposed_patches: int = 0
    telemetry_events: int = 0


class SecurityScanResult(BaseModel):
    scanner: str
    scope: str
    finding_count: int
    findings: list[dict[str, object]] = Field(default_factory=list)


class DocPatch(BaseModel):
    """A proposed documentation edit; never written to disk by the tool itself."""

    path: str
    section: str
    content: str


class DocsUpdateProposal(BaseModel):
    scope: str
    proposed_patches: list[DocPatch] = Field(default_factory=list)
    summary: str = ""

