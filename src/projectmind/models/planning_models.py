"""Hierarchical execution planning models."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PlanTask(BaseModel):
    id: str
    title: str
    parent_id: str | None = None
    level: str
    status: str = "todo"
    checkpoints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class HierarchicalPlan(BaseModel):
    plan_id: str
    goal: str
    tasks: list[PlanTask]
    prompt_template: str


class RiskItem(BaseModel):
    description: str
    probability: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=1)
    mitigation: str

    @model_validator(mode="after")
    def validate_score(self) -> RiskItem:
        expected = self.probability * self.impact
        if abs(expected - self.score) > 1e-8:
            raise ValueError("risk score must equal probability * impact")
        return self


class ImplementationComparison(BaseModel):
    criteria: list[str]
    option_a: str
    option_b: str
    advantages_a: list[str] = Field(default_factory=list)
    advantages_b: list[str] = Field(default_factory=list)
    disadvantages_a: list[str] = Field(default_factory=list)
    disadvantages_b: list[str] = Field(default_factory=list)
    estimated_cost_a: str
    estimated_cost_b: str
    migration_effort_a: str
    migration_effort_b: str
    recommendation: str


class LongRunningTask(BaseModel):
    id: str
    spec: str
    plan_id: str | None = None
    status: str
    checkpoints: list[str] = Field(default_factory=list)
    post_mortem_memory_id: str | None = None

