"""Convention-aware boilerplate descriptions with no filesystem mutation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, Field

from projectmind.memory.store import MemoryStore
from projectmind.models.memory_models import MemoryType


class ConventionReference(BaseModel):
    memory_id: str
    summary: str
    score: float = Field(ge=0, le=1)


class ProposedArtifact(BaseModel):
    logical_name: str
    purpose: str
    content_outline: list[str] = Field(default_factory=list)


class BoilerplateProposal(BaseModel):
    pattern: str
    description: str
    artifacts: list[ProposedArtifact]
    conventions_used: list[ConventionReference] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    prompt_template: str
    capability_mode: Literal["deterministic"] = "deterministic"
    writes_files: Literal[False] = False


BOILERPLATE_PROMPT = """Propose boilerplate; do not write files.
1) Cite applicable project conventions and examples. 2) State missing conventions and assumptions.
3) Describe each proposed artefact, responsibility, public boundary, and tests. 4) Return the
proposal for review through the normal propose -> confirm -> apply workflow."""


def _context_text(context: str | Mapping[str, object]) -> str:
    if isinstance(context, str):
        value = context.strip()
    else:
        value = json.dumps(dict(context), ensure_ascii=False, sort_keys=True, default=str).strip()
    if not value:
        raise ValueError("context cannot be empty")
    return value


def _artifact_descriptions(pattern: str) -> list[ProposedArtifact]:
    folded = pattern.casefold()
    if any(marker in folded for marker in ("endpoint", "route", "api")):
        return [
            ProposedArtifact(
                logical_name="endpoint module",
                purpose=(
                    "Expose the requested transport boundary using the project's route convention."
                ),
                content_outline=[
                    "input validation",
                    "domain delegation",
                    "structured error mapping",
                ],
            ),
            ProposedArtifact(
                logical_name="request/response models",
                purpose=(
                    "Define typed boundary contracts without leaking transport concerns into "
                    "domain code."
                ),
                content_outline=["validated input", "stable output", "error schema"],
            ),
            ProposedArtifact(
                logical_name="endpoint tests",
                purpose="Cover success, invalid input, authorization, and domain failure mapping.",
            ),
        ]
    if any(marker in folded for marker in ("command", "cli")):
        return [
            ProposedArtifact(
                logical_name="command module",
                purpose="Bind CLI arguments to an existing domain service.",
                content_outline=["typed options", "service call", "stable exit/error behaviour"],
            ),
            ProposedArtifact(
                logical_name="command tests",
                purpose="Verify invocation, output, exit status, and invalid input.",
            ),
        ]
    if any(marker in folded for marker in ("service", "adapter", "provider")):
        return [
            ProposedArtifact(
                logical_name="service boundary",
                purpose="Define the stable typed contract and implementation responsibility.",
                content_outline=[
                    "protocol/interface",
                    "deterministic fallback",
                    "provider implementation",
                ],
            ),
            ProposedArtifact(
                logical_name="service tests",
                purpose=(
                    "Verify the contract, fallback, provider failure, and capability reporting."
                ),
            ),
        ]
    return [
        ProposedArtifact(
            logical_name="implementation module",
            purpose="Contain the requested pattern at the project-approved boundary.",
            content_outline=["typed public API", "validation", "explicit failure behaviour"],
        ),
        ProposedArtifact(
            logical_name="targeted tests",
            purpose="Demonstrate acceptance criteria and relevant edge cases.",
        ),
    ]


def generate_boilerplate(
    pattern: str,
    context: str | Mapping[str, object],
    *,
    memory_store: MemoryStore | None = None,
    convention_limit: int = 5,
) -> BoilerplateProposal:
    """Return descriptions only; source creation remains an execution-layer operation."""

    clean_pattern = pattern.strip()
    if not clean_pattern:
        raise ValueError("pattern cannot be empty")
    clean_context = _context_text(context)
    if not 1 <= convention_limit <= 20:
        raise ValueError("convention_limit must be between 1 and 20")

    conventions: list[ConventionReference] = []
    if memory_store is not None:
        matches = memory_store.search(
            f"{clean_pattern} {clean_context}",
            memory_type=MemoryType.CONVENTION,
            limit=convention_limit,
        )
        conventions = [
            ConventionReference(
                memory_id=result.entry.id,
                summary=result.entry.summary or result.entry.content,
                score=result.score,
            )
            for result in matches
        ]

    assumptions = [
        "Exact file paths and names require repository inspection and user review.",
        "No source file is created or modified by this proposal.",
    ]
    if not conventions:
        assumptions.append(
            "No matching convention memory was available; do not infer a house style."
        )
    else:
        assumptions.append("Retrieved conventions must be checked against current source examples.")
    return BoilerplateProposal(
        pattern=clean_pattern,
        description=(
            f"Describe boilerplate for {clean_pattern!r} in the supplied context. "
            "The artefacts below are responsibilities and outlines only, not generated file "
            "contents."
        ),
        artifacts=_artifact_descriptions(clean_pattern),
        conventions_used=conventions,
        assumptions=assumptions,
        prompt_template=BOILERPLATE_PROMPT,
    )
