from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> datetime:
    return datetime.now(UTC)


class Provenance(str, Enum):
    code_fact = "code_fact"
    test_result = "test_result"
    user_decision = "user_decision"
    llm_inference = "llm_inference"
    git_history = "git_history"
    external_doc = "external_doc"


class Evidence(BaseModel):
    source: str
    excerpt: str = ""
    kind: str = "code"
    confidence: float = Field(1.0, ge=0, le=1)


class Decision(BaseModel):
    title: str
    decision: str
    rationale: str = ""
    alternatives: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.user_decision
    confidence: float = Field(0.9, ge=0, le=1)


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    done_when: list[str] = Field(default_factory=list)
    status: Literal["pending", "in_progress", "done", "blocked"] = "pending"


class VerifiedPlan(BaseModel):
    model_config = ConfigDict(extra="allow")
    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    objective: str
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)
    test_strategy: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(default_factory=list)
    status: Literal["draft", "validated", "blocked", "done"] = "draft"


class DebugHypothesis(BaseModel):
    hypothesis_id: str = Field(default_factory=lambda: str(uuid4()))
    statement: str
    evidence_for: list[Evidence] = Field(default_factory=list)
    evidence_against: list[Evidence] = Field(default_factory=list)
    diagnostic_test: str = ""
    probability: float = Field(0.5, ge=0, le=1)
    test_cost: float = Field(1, gt=0)
    confidence: float = Field(0.5, ge=0, le=1)

    @property
    def priority(self) -> float:
        return self.probability / self.test_cost


class ProposedEdit(BaseModel):
    edit_id: str = Field(default_factory=lambda: str(uuid4()))
    file_path: str
    old_content: str
    new_content: str
    diff: str
    risks: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    critique_verdict: str | None = None


class ContextMode(str, Enum):
    exploratory = "exploratory"
    surgical = "surgical"
    debug = "debug"


class Feedback(BaseModel):
    context_ref: str
    signal: Literal["up", "down"]
    note: str = ""


class ScoringWeights(BaseModel):
    graph_relevance: float = 0.35
    semantic_similarity: float = 0.25
    lexical_match: float = 0.20
    recency_git: float = 0.10
    architectural_importance: float = 0.10


class TelemetryEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    ref: str = ""
    justification: str = ""
    status: str = "ok"
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)


class AlternativeComparison(BaseModel):
    alternatives: list[dict[str, Any]]
    selected: str | None = None
    rationale: str = ""


class RefactoringSuggestion(BaseModel):
    target: str
    smell: str
    rationale: str
    expected_impact: str
    confidence: float = Field(0.7, ge=0, le=1)


class ThoughtStep(BaseModel):
    step_index: int
    thought: str
    success_criteria: list[str] = Field(default_factory=list)
    status: Literal["passed", "failed", "blocked"] = "passed"
    blocked_reason: str | None = None
    next_step_suggested: str | None = None
    confidence: float = Field(0.5, ge=0, le=1)


class ReasoningSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    task: str
    current_step: int = 0
    status: Literal["active", "blocked", "complete"] = "active"
    steps: list[ThoughtStep] = Field(default_factory=list)


class Alternative(BaseModel):
    branch_id: str = Field(default_factory=lambda: str(uuid4()))
    proposal: str
    score: float = 0
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    verdict: Literal["approve", "revise", "reject"]
    findings: list[str] = Field(default_factory=list)
    suggested_tests: list[str] = Field(default_factory=list)
    perspectives: list[str] = Field(default_factory=list)
    overall_score: float = Field(0, ge=0, le=100)


class RiskEntry(BaseModel):
    title: str
    probability: float = Field(0, ge=0, le=1)
    impact: float = Field(0, ge=0, le=1)
    mitigation: str = ""
    tier: Literal["low", "medium", "high", "critical"] = "low"

    @property
    def score(self) -> float:
        return self.probability * self.impact


class Hypothesis(DebugHypothesis):
    pass


class Learning(BaseModel):
    task_ref: str
    outcome: str
    what_went_well: str = ""
    what_failed: str = ""
    lessons: list[str] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=list)


class ConfidenceScore(BaseModel):
    score: int = Field(0, ge=0, le=100)
    justification: str
    uncertainty_sources: list[str] = Field(default_factory=list)


class UsageRecord(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    model: str = "local"
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_hit: bool = False
    cost_usd: float = 0.0
    ref: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)
