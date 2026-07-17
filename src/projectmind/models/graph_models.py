"""Architectural graph models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ROUTE = "route"
    DB_TABLE = "db_table"
    TEST = "test"
    WORKSPACE = "workspace"


class EdgeType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    TESTS = "tests"
    ROUTES_TO = "routes_to"
    READS_WRITES_TABLE = "reads_writes_table"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    name: str
    qualname: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    language: str
    complexity: float | None = None
    loc: int | None = None
    method_count: int = 0
    centrality: float | None = None
    test_coverage: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source_id: str
    target_id: str | None = None
    target_ref: str | None = None
    type: EdgeType
    weight: float = Field(default=1.0, gt=0)
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence: dict[str, object] = Field(default_factory=dict)


class CodeSmell(BaseModel):
    node_id: str
    smell_type: str
    severity: str
    description: str
    suggestion: str | None = None
    evidence: dict[str, object] = Field(default_factory=dict)


class GraphSummary(BaseModel):
    scope: str
    files: int
    nodes: int
    edges: int
    languages: dict[str, int] = Field(default_factory=dict)
    node_types: dict[str, int] = Field(default_factory=dict)
    index_revision: int


class ImpactResult(BaseModel):
    target: str
    direct_dependents: list[str] = Field(default_factory=list)
    transitive_dependents: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    risk: str = "low"
    rationale: list[str] = Field(default_factory=list)


class SimulationReport(BaseModel):
    """Result of a disk-free change simulation over an in-memory graph copy."""

    proposed_change: str
    affected_files: list[str] = Field(default_factory=list)
    introduced_cycles: list[list[str]] = Field(default_factory=list)
    affected_tests: list[str] = Field(default_factory=list)
    estimated_impact_nodes: int = 0
    notes: list[str] = Field(default_factory=list)

