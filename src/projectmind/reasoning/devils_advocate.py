"""Structured counterarguments as a cognitive forcing function."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CounterArgument(BaseModel):
    category: str
    challenge: str
    evidence_needed: str
    mitigation: str


class DevilsAdvocateResult(BaseModel):
    proposal: str
    counterarguments: list[CounterArgument] = Field(min_length=1)
    prompt_template: str
    caveat: str


DEVILS_ADVOCATE_PROMPT = """Challenge the proposal, not the author.
Test its assumptions, failure modes, rollback, operational burden, and simplest viable
alternative. Separate observed evidence from questions. A challenge is not a factual defect
until evidence confirms it."""


def play_devils_advocate(proposal: str) -> DevilsAdvocateResult:
    """Return reusable challenges without fabricating proposal-specific defects."""

    clean_proposal = proposal.strip()
    if not clean_proposal:
        raise ValueError("proposal cannot be empty")
    counterarguments = [
        CounterArgument(
            category="Assumptions",
            challenge="A key constraint may be implicit or based on stale project knowledge.",
            evidence_needed="List assumptions and cite the current source for each one.",
            mitigation="Turn unverified assumptions into discovery checkpoints before mutation.",
        ),
        CounterArgument(
            category="Failure modes",
            challenge=(
                "The happy path may hide partial failure, concurrency, or malformed-input cases."
            ),
            evidence_needed="Enumerate failure signals and tests for the highest-impact cases.",
            mitigation="Add bounded validation and explicit error handling at the owning boundary.",
        ),
        CounterArgument(
            category="Rollback",
            challenge="The change may not be safely reversible after data or callers migrate.",
            evidence_needed="Provide a rollback trigger, procedure, and compatibility window.",
            mitigation="Stage irreversible work and preserve a tested rollback path.",
        ),
        CounterArgument(
            category="Operational cost",
            challenge=(
                "Maintenance, observability, or on-call cost may exceed the implementation benefit."
            ),
            evidence_needed="Estimate ownership, telemetry, failure recovery, and lifecycle costs.",
            mitigation="Assign ownership and acceptance thresholds before adopting new machinery.",
        ),
        CounterArgument(
            category="Simpler alternative",
            challenge=(
                "A smaller change or evidence-first spike may satisfy the same acceptance criteria."
            ),
            evidence_needed="Compare at least one lower-complexity option using the same criteria.",
            mitigation="Prefer the least complex option whose evidence satisfies the requirements.",
        ),
    ]
    return DevilsAdvocateResult(
        proposal=clean_proposal,
        counterarguments=counterarguments,
        prompt_template=DEVILS_ADVOCATE_PROMPT,
        caveat="These are hypotheses to verify, not claims that the proposal is defective.",
    )
