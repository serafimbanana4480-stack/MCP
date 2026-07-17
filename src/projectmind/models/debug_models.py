"""Structured debugging and quality-assurance models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from projectmind.models.reasoning_models import Hypothesis


class RelatedBug(BaseModel):
    memory_id: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    matched_terms: list[str] = Field(default_factory=list)
    related_paths: list[str] = Field(default_factory=list)


class RootCauseCandidate(BaseModel):
    path: str
    line: int | None = None
    symbol: str | None = None
    score: float = Field(ge=0, le=1)
    rationale: list[str] = Field(default_factory=list)


class RootCauseReport(BaseModel):
    error_summary: str
    candidates: list[RootCauseCandidate] = Field(default_factory=list)
    related_bugs: list[RelatedBug] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReproductionProposal(BaseModel):
    test_path: str
    test_content: str
    target_paths: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    requires_review: bool = True


class NormalizedDiagnostic(BaseModel):
    tool: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    severity: str
    code: str | None = None
    message: str


class RegressionPlan(BaseModel):
    changed_targets: list[str]
    related_tests: list[str] = Field(default_factory=list)
    commands: list[list[str]] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)

