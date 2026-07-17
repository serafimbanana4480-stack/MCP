"""Visible planning, validation, and critique models (not hidden chain-of-thought)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED = "failed"


class ThoughtStep(BaseModel):
    id: str
    plan_id: str
    step_number: int = Field(ge=1)
    description: str
    success_criteria: str
    status: StepStatus = StepStatus.PENDING
    evidence: str | None = None


class SequentialPlan(BaseModel):
    plan_id: str
    task: str
    steps: list[ThoughtStep]
    prompt_template: str
    capability_mode: str = "deterministic"


class Hypothesis(BaseModel):
    description: str
    probability: float = Field(ge=0, le=1)
    test_cost: str
    test_procedure: str
    evidence: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    perspective: str
    issues: list[str] = Field(default_factory=list)
    severity: str
    recommendation: str


class ConfidenceScore(BaseModel):
    score: int = Field(ge=0, le=100)
    justification: str
    supporting_evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class Alternative(BaseModel):
    title: str
    approach: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: ConfidenceScore


class AlternativesResult(BaseModel):
    task: str
    alternatives: list[Alternative]
    recommended_index: int
    recommendation: str
    prompt_template: str
    capability_mode: str = "deterministic"


class ReactResult(BaseModel):
    task_id: str
    iteration: int
    next_thought: str
    suggested_action: str
    suggested_arguments: dict[str, object] = Field(default_factory=dict)
    should_stop: bool = False
    warning: str | None = None

