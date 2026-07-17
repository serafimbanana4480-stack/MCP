"""Evidence-based improvement recommendations that never self-apply."""

from __future__ import annotations

from pydantic import BaseModel, Field

from projectmind.telemetry.events import TelemetryStore


class ImprovementSuggestion(BaseModel):
    title: str
    rationale: str
    action: str
    evidence: dict[str, object] = Field(default_factory=dict)


class ImprovementReport(BaseModel):
    suggestions: list[ImprovementSuggestion]
    applied_automatically: bool = False


class SelfImprovementReporter:
    def __init__(self, telemetry: TelemetryStore) -> None:
        self.telemetry = telemetry

    def report(self) -> ImprovementReport:
        stats = self.telemetry.usage_stats()
        calls = int(str(stats["calls"]))
        success_rate = float(str(stats["success_rate"]))
        average_latency = float(str(stats["average_latency_ms"]))
        raw_tools = stats.get("tools", [])
        tools = [str(item) for item in raw_tools] if isinstance(raw_tools, list) else []
        suggestions: list[ImprovementSuggestion] = []

        if calls == 0:
            suggestions.append(
                ImprovementSuggestion(
                    title="Collect a representative local baseline",
                    rationale=(
                        "No tool telemetry exists, so ranking and latency changes "
                        "cannot be evaluated."
                    ),
                    action=(
                        "Run indexing, retrieval, and planning scenarios before tuning defaults."
                    ),
                    evidence={"calls": 0},
                )
            )
        if calls and success_rate < 0.95:
            suggestions.append(
                ImprovementSuggestion(
                    title="Investigate the highest-failure tools",
                    rationale="Observed tool success is below the 95% operational target.",
                    action=(
                        "Group local failures by tool and fix deterministic errors "
                        "before tuning retrieval."
                    ),
                    evidence={"success_rate": success_rate},
                )
            )
        if average_latency > 500:
            suggestions.append(
                ImprovementSuggestion(
                    title="Profile slow tool paths",
                    rationale="Mean latency exceeds 500 ms.",
                    action=(
                        "Inspect per-tool latency and add bounded caching only to "
                        "stable read paths."
                    ),
                    evidence={"average_latency_ms": average_latency},
                )
            )
        suggestions.append(
            ImprovementSuggestion(
                title="Review retrieval feedback coverage",
                rationale=(
                    "Feedback is meaningful only when both positive and negative "
                    "outcomes are recorded."
                ),
                action=(
                    "Compare memory feedback counts with retrieval calls before "
                    "changing weights."
                ),
                evidence={"tool_rows": len(tools)},
            )
        )
        suggestions.append(
            ImprovementSuggestion(
                title="Validate cache effectiveness after index changes",
                    rationale=(
                        "Context cache entries must never survive a changed index revision."
                    ),
                action=(
                    "Track cache hit rate alongside revision invalidations in the benchmark suite."
                ),
                evidence={"calls": calls},
            )
        )
        return ImprovementReport(suggestions=suggestions)

