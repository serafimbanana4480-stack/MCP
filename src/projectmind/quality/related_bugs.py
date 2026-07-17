"""Related-bug retrieval and evidence-ranked root-cause candidates."""

from __future__ import annotations

import math
import re
from pathlib import Path

from projectmind.database import Database
from projectmind.models.debug_models import (
    RelatedBug,
    RootCauseCandidate,
    RootCauseReport,
)
from projectmind.models.reasoning_models import Hypothesis

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
PYTHON_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)(?:, in ([^\n]+))?')
GENERIC_FRAME_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[^\s():]+\.(?:py|js|jsx|ts|tsx|go|rs|java)):(?P<line>\d+)"
)


def _terms(value: str) -> set[str]:
    ignored = {"error", "exception", "traceback", "failed", "with", "from", "line"}
    return {term.casefold() for term in WORD_RE.findall(value) if term.casefold() not in ignored}


def _overlap_score(query: set[str], content: str) -> tuple[float, list[str]]:
    if not query:
        return 0.0, []
    content_terms = _terms(content)
    matches = sorted(query & content_terms)
    return min(1.0, len(matches) / max(1.0, math.sqrt(len(query)))), matches


class DebugService:
    def __init__(self, database: Database, project_root: Path) -> None:
        self.database = database
        self.project_root = project_root.resolve()

    def detect_related_bugs(self, description: str, *, limit: int = 10) -> list[RelatedBug]:
        query = _terms(description)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, content, summary, confidence
                FROM memories
                WHERE type = 'bug' AND status = 'active' AND superseded_by IS NULL
                ORDER BY created_at DESC
                """
            ).fetchall()
            related_nodes: dict[str, list[str]] = {
                str(row["memory_id"]): []
                for row in connection.execute("SELECT memory_id FROM memory_nodes").fetchall()
            }
            for row in connection.execute(
                """
                SELECT mn.memory_id, COALESCE(n.path, mn.node_id) AS path
                FROM memory_nodes mn LEFT JOIN nodes n ON n.id = mn.node_id
                """
            ).fetchall():
                related_nodes.setdefault(str(row["memory_id"]), []).append(str(row["path"]))

        ranked: list[tuple[float, RelatedBug]] = []
        for row in rows:
            searchable = f"{row['summary'] or ''} {row['content']}"
            lexical, matches = _overlap_score(query, searchable)
            confidence = float(row["confidence"])
            score = 0.65 * lexical + 0.35 * confidence
            if lexical == 0 and query:
                continue
            ranked.append(
                (
                    score,
                    RelatedBug(
                        memory_id=str(row["id"]),
                        summary=str(row["summary"] or row["content"]),
                        confidence=min(1.0, score),
                        matched_terms=matches,
                        related_paths=sorted(set(related_nodes.get(str(row["id"]), []))),
                    ),
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1].memory_id))
        return [item for _, item in ranked[: max(1, limit)]]

    def root_cause_analysis(self, error: str) -> RootCauseReport:
        frames = self._parse_frames(error)
        candidates: dict[tuple[str, int | None], RootCauseCandidate] = {}
        with self.database.connect() as connection:
            for position, (raw_path, line, function) in enumerate(frames):
                relative = self._relative_candidate(raw_path)
                if relative is None:
                    continue
                node = connection.execute(
                    """
                    SELECT id, name, qualname, start_line, end_line
                    FROM nodes
                    WHERE path = ? AND (? IS NULL OR (start_line <= ? AND end_line >= ?))
                    ORDER BY (end_line - start_line) ASC LIMIT 1
                    """,
                    (relative, line, line, line),
                ).fetchone()
                stack_score = max(0.4, 1.0 - position * 0.08)
                rationale = [f"stack frame #{position + 1}"]
                symbol = function.strip() if function else None
                if node is not None:
                    symbol = str(node["qualname"])
                    stack_score = min(1.0, stack_score + 0.15)
                    rationale.append("line intersects an indexed symbol")
                    callers = connection.execute(
                        "SELECT COUNT(*) FROM edges WHERE target_id = ?",
                        (node["id"],),
                    ).fetchone()[0]
                    if int(callers) > 0:
                        stack_score = min(1.0, stack_score + min(0.15, int(callers) * 0.02))
                        rationale.append(f"symbol has {callers} indexed incoming relation(s)")
                candidates[(relative, line)] = RootCauseCandidate(
                    path=relative,
                    line=line,
                    symbol=symbol,
                    score=stack_score,
                    rationale=rationale,
                )

        related = self.detect_related_bugs(error, limit=5)
        ordered = sorted(
            candidates.values(), key=lambda item: (-item.score, item.path, item.line or 0)
        )
        hypotheses = self._hypotheses(error, ordered, related)
        first_line = next(
            (line.strip() for line in error.splitlines() if line.strip()), "unknown error"
        )
        warnings = [] if ordered else ["No indexed stack frame matched the project graph."]
        return RootCauseReport(
            error_summary=first_line[:500],
            candidates=ordered,
            related_bugs=related,
            hypotheses=hypotheses,
            warnings=warnings,
        )

    @staticmethod
    def _parse_frames(error: str) -> list[tuple[str, int | None, str | None]]:
        frames: list[tuple[str, int | None, str | None]] = []
        occupied: set[tuple[str, int]] = set()
        for match in PYTHON_FRAME_RE.finditer(error):
            path, line, function = match.group(1), int(match.group(2)), match.group(3)
            frames.append((path, line, function))
            occupied.add((path, line))
        for match in GENERIC_FRAME_RE.finditer(error):
            path, line = match.group("path"), int(match.group("line"))
            if (path, line) not in occupied:
                frames.append((path, line, None))
        return frames

    def _relative_candidate(self, raw_path: str) -> str | None:
        normalized = raw_path.replace("\\", "/")
        raw = Path(raw_path)
        if raw.is_absolute():
            try:
                return raw.resolve().relative_to(self.project_root).as_posix()
            except (OSError, ValueError):
                return None
        parts = normalized.split("/")
        for start in range(len(parts)):
            candidate = "/".join(parts[start:])
            if (self.project_root / candidate).exists():
                return candidate
        return normalized.lstrip("./")

    @staticmethod
    def _hypotheses(
        error: str,
        candidates: list[RootCauseCandidate],
        related: list[RelatedBug],
    ) -> list[Hypothesis]:
        hypotheses: list[Hypothesis] = []
        if candidates:
            first = candidates[0]
            hypotheses.append(
                Hypothesis(
                    description=f"The failure originates in {first.symbol or first.path}.",
                    probability=min(0.9, first.score),
                    test_cost="low",
                    test_procedure=(
                        f"Run the narrowest test exercising {first.path}:{first.line or 1}."
                    ),
                    evidence=first.rationale,
                )
            )
        if related:
            hypotheses.append(
                Hypothesis(
                    description="The failure repeats a previously recorded bug pattern.",
                    probability=min(0.85, related[0].confidence),
                    test_cost="low",
                    test_procedure=(
                        f"Compare current inputs and fix with memory {related[0].memory_id}."
                    ),
                    evidence=related[0].matched_terms,
                )
            )
        lowered = error.casefold()
        patterns = [
            ("none", "A missing/null value violates an unchecked invariant."),
            ("timeout", "A dependency or concurrency boundary exceeded its time budget."),
            ("permission", "Runtime permissions differ from the expected environment."),
            ("connection", "An external dependency is unavailable or misconfigured."),
        ]
        for token, description in patterns:
            if token in lowered:
                hypotheses.append(
                    Hypothesis(
                        description=description,
                        probability=0.5,
                        test_cost="low",
                        test_procedure=(
                            f"Reproduce with the {token} boundary isolated and instrumented."
                        ),
                        evidence=[f"error text contains {token!r}"],
                    )
                )
        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    description="The observed error requires a minimal deterministic reproduction.",
                    probability=0.4,
                    test_cost="medium",
                    test_procedure=(
                        "Reduce the failing input while preserving the first stable stack frame."
                    ),
                )
            )
        return sorted(hypotheses, key=lambda item: (-item.probability, item.test_cost))

