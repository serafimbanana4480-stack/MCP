"""Central hybrid retrieval orchestrator."""

from __future__ import annotations

import hashlib
import math
import sqlite3
from collections import defaultdict, deque
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from projectmind.config import RetrievalConfig
from projectmind.database import Database
from projectmind.memory.store import MemoryStore
from projectmind.models.common import Provenance, utc_now
from projectmind.models.memory_models import MemorySearchResult, MemoryType
from projectmind.models.retrieval_models import ContextBundle, ContextItem
from projectmind.retrieval.cache import ContextCache
from projectmind.retrieval.hierarchical_rag import (
    RankedContext,
    estimate_tokens,
    fit_context_to_budget,
)
from projectmind.retrieval.scoring import hybrid_score, lexical_match

RetrievalMode = Literal["exploratory", "surgical", "debug"]
SemanticScorer = Callable[[str, str], float]


class RetrievalEngine:
    """Build bounded context from chunks, architecture, and persistent memories."""

    def __init__(
        self,
        database: Database,
        memory_store: MemoryStore | None = None,
        config: RetrievalConfig | None = None,
        *,
        semantic_scorer: SemanticScorer | None = None,
        semantic_cache_key: str | None = None,
        cache: ContextCache | None = None,
    ) -> None:
        self.database = database
        self.memory_store = memory_store or MemoryStore(database)
        self.config = config or RetrievalConfig()
        self.semantic_scorer = semantic_scorer
        self.semantic_cache_key = semantic_cache_key or self._semantic_identity(semantic_scorer)
        self.cache = cache or ContextCache(database)

    def get_relevant_context(
        self,
        task: str,
        mode: RetrievalMode = "surgical",
        token_budget: int = 4_000,
        include_memory: bool = True,
        depth: int = 2,
        *,
        branch: str | None = None,
    ) -> ContextBundle:
        """Return explainable context that strictly respects ``token_budget``."""

        clean_task = task.strip()
        if not clean_task:
            raise ValueError("task cannot be empty")
        if mode not in {"exploratory", "surgical", "debug"}:
            raise ValueError(f"unsupported retrieval mode: {mode}")
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        if depth < 0:
            raise ValueError("depth cannot be negative")
        effective_depth = self._effective_depth(mode, depth)
        weight_values = self.config.scoring_weights.model_dump()
        cache_key = self.cache.key(
            clean_task,
            mode=mode,
            token_budget=token_budget,
            include_memory=include_memory,
            depth=effective_depth,
            branch=branch,
            extra={
                **{key: float(value) for key, value in weight_values.items()},
                "semantic": self.semantic_cache_key,
            },
        )
        revision = self.database.index_revision()
        cached = self.cache.get(cache_key, index_revision=revision)
        if cached is not None:
            return cached

        with self.database.connect() as connection:
            nodes = connection.execute(
                """
                SELECT n.*, f.mtime_ns, f.indexed_at
                FROM nodes AS n
                LEFT JOIN files AS f ON f.path = n.path
                ORDER BY n.id
                """
            ).fetchall()
            chunks = connection.execute(
                """
                SELECT
                    c.*, n.type AS node_type, n.name AS node_name, n.qualname,
                    n.centrality, n.test_coverage, f.mtime_ns, f.indexed_at
                FROM chunks AS c
                LEFT JOIN nodes AS n ON n.id = c.node_id
                LEFT JOIN files AS f ON f.path = c.path
                ORDER BY c.id
                """
            ).fetchall()
            edges = connection.execute(
                "SELECT source_id, target_id FROM edges WHERE target_id IS NOT NULL"
            ).fetchall()
            node_feedback = self._node_feedback(connection)

        seed_ids = self._seed_nodes(clean_task, nodes, mode)
        distances = self._graph_distances(seed_ids, edges, effective_depth)
        path_distances = self._path_distances(nodes, distances)
        weights = self._mode_weights(mode)
        ranked: list[RankedContext] = []
        ranked.extend(
            self._code_candidates(
                clean_task,
                chunks,
                mode=mode,
                distances=distances,
                path_distances=path_distances,
                feedback=node_feedback,
                weights=weights,
            )
        )
        ranked.extend(
            self._graph_candidates(
                clean_task,
                nodes,
                mode=mode,
                distances=distances,
                feedback=node_feedback,
                weights=weights,
            )
        )
        if include_memory:
            ranked.extend(
                self._memory_candidates(clean_task, mode=mode, branch=branch, weights=weights)
            )

        effective_budget = self._mode_budget(mode, token_budget)
        selected, tokens_used = fit_context_to_budget(
            ranked,
            effective_budget,
            minimum_item_tokens=min(12, effective_budget),
        )
        warnings: list[str] = []
        semantic_values = [candidate.item.score.semantic_similarity for candidate in ranked]
        if self.config.scoring_weights.semantic_similarity > 0 and not any(
            value is not None for value in semantic_values
        ):
            warnings.append(
                "Semantic similarity unavailable; available scoring signals were renormalized."
            )
        if not chunks:
            warnings.append("No indexed code chunks are available.")
        if ranked and not selected:
            warnings.append("The token budget was too small for the available context.")
        if effective_budget < token_budget:
            warnings.append(
                f"{mode} mode intentionally used at most {effective_budget} "
                f"of {token_budget} tokens."
            )
        graph_summary = self._graph_summary(
            nodes=nodes,
            edges=edges,
            seeds=seed_ids,
            depth=effective_depth,
            selected=selected,
        )
        bundle = ContextBundle(
            task=clean_task,
            mode=mode,
            items=selected,
            graph_summary=graph_summary,
            tokens_used=tokens_used,
            token_budget=token_budget,
            cache_hit=False,
            warnings=warnings,
        )
        self.cache.put(cache_key, bundle, index_revision=revision)
        return bundle

    def find_similar_past_solutions(
        self,
        task_description: str,
        *,
        branch: str | None = None,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """Analogical fallback over solved bugs, lessons, and historical plans."""

        results: list[MemorySearchResult] = []
        for memory_type in (MemoryType.BUG, MemoryType.LESSON, MemoryType.PLAN):
            results.extend(
                self.memory_store.search(
                    task_description,
                    memory_type=memory_type,
                    current_branch=branch,
                    include_global=True,
                    limit=limit,
                )
            )
        results.sort(key=lambda result: (-result.score, result.entry.id))
        return results[:limit]

    def _code_candidates(
        self,
        task: str,
        rows: Sequence[sqlite3.Row],
        *,
        mode: RetrievalMode,
        distances: Mapping[str, int],
        path_distances: Mapping[str, int],
        feedback: Mapping[str, float],
        weights: Mapping[str, float],
    ) -> list[RankedContext]:
        candidates: list[RankedContext] = []
        for row in rows:
            node_id = str(row["node_id"]) if row["node_id"] is not None else None
            path = str(row["path"])
            content = str(row["content"])
            descriptor = " ".join(
                str(value)
                for value in (path, row["node_name"], row["qualname"], content)
                if value is not None
            )
            lexical = lexical_match(task, descriptor)
            semantic = self._semantic(task, content)
            distance = distances.get(node_id) if node_id else None
            if distance is None:
                distance = path_distances.get(path)
            graph = self._distance_score(distance, has_seeds=bool(distances))
            is_test = self._is_test(str(row["node_type"] or ""), path)
            if (
                mode == "surgical"
                and lexical == 0
                and not semantic
                and (distance is None or distance > 1)
            ):
                continue
            raw_feedback = feedback.get(node_id) if node_id else None
            breakdown = hybrid_score(
                graph_relevance=graph,
                semantic_similarity=semantic,
                lexical_match=lexical,
                recency_git=self._recency(row["mtime_ns"], row["indexed_at"]),
                architectural_importance=self._bounded_optional(row["centrality"]),
                test_coverage_bonus=(
                    1.0
                    if mode == "debug" and is_test
                    else self._bounded_optional(row["test_coverage"])
                ),
                feedback_score=(raw_feedback + 1.0) / 2.0 if raw_feedback is not None else None,
                weights=weights,
            )
            summary_value = str(row["summary"]).strip() if row["summary"] else ""
            hierarchy_summary = summary_value or self._chunk_summary(row)
            provenance = Provenance(
                kind="chunk",
                reference=str(row["id"]),
                path=path,
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                content_hash=str(row["content_hash"]),
                confidence=breakdown.final_score,
            )
            item = ContextItem(
                kind="code",
                content=content,
                path=path,
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                token_estimate=max(int(row["token_estimate"]), estimate_tokens(content)),
                score=breakdown,
                provenance=provenance,
            )
            priority = 0 if (mode == "debug" and is_test) else 1
            candidates.append(
                RankedContext(item=item, summary=hierarchy_summary, hierarchy=priority)
            )
        return candidates

    def _graph_candidates(
        self,
        task: str,
        rows: Sequence[sqlite3.Row],
        *,
        mode: RetrievalMode,
        distances: Mapping[str, int],
        feedback: Mapping[str, float],
        weights: Mapping[str, float],
    ) -> list[RankedContext]:
        candidates: list[RankedContext] = []
        for row in rows:
            node_id = str(row["id"])
            path = str(row["path"])
            descriptor = f"{row['type']} {row['qualname']} {path}"
            lexical = lexical_match(task, descriptor)
            semantic = self._semantic(task, descriptor)
            distance = distances.get(node_id)
            is_test = self._is_test(str(row["type"]), path)
            if mode == "surgical" and lexical == 0 and not semantic and distance is None:
                continue
            if (
                mode == "debug"
                and lexical == 0
                and not semantic
                and distance is None
                and not is_test
            ):
                continue
            raw_feedback = feedback.get(node_id)
            breakdown = hybrid_score(
                graph_relevance=self._distance_score(distance, has_seeds=bool(distances)),
                semantic_similarity=semantic,
                lexical_match=lexical,
                recency_git=self._recency(row["mtime_ns"], row["indexed_at"]),
                architectural_importance=self._bounded_optional(row["centrality"]),
                test_coverage_bonus=(
                    1.0
                    if mode == "debug" and is_test
                    else self._bounded_optional(row["test_coverage"])
                ),
                feedback_score=(raw_feedback + 1.0) / 2.0 if raw_feedback is not None else None,
                weights=weights,
            )
            line_suffix = ""
            if row["start_line"] is not None:
                line_suffix = f":{row['start_line']}"
                if row["end_line"] is not None:
                    line_suffix += f"-{row['end_line']}"
            content = f"{row['type']} {row['qualname']} — {path}{line_suffix}"
            item = ContextItem(
                kind="graph",
                content=content,
                path=path,
                start_line=int(row["start_line"]) if row["start_line"] is not None else None,
                end_line=int(row["end_line"]) if row["end_line"] is not None else None,
                token_estimate=estimate_tokens(content),
                score=breakdown,
                provenance=Provenance(
                    kind="node",
                    reference=node_id,
                    path=path,
                    start_line=(
                        int(row["start_line"]) if row["start_line"] is not None else None
                    ),
                    end_line=int(row["end_line"]) if row["end_line"] is not None else None,
                    confidence=breakdown.final_score,
                ),
            )
            candidates.append(RankedContext(item=item, hierarchy=0))
        return candidates

    def _memory_candidates(
        self,
        task: str,
        *,
        mode: RetrievalMode,
        branch: str | None,
        weights: Mapping[str, float],
    ) -> list[RankedContext]:
        results = self.memory_store.search(
            task,
            current_branch=branch,
            include_global=True,
            limit=40 if mode == "exploratory" else 15,
        )
        if self.semantic_scorer is not None:
            semantic_pool = self.memory_store.search(
                "",
                current_branch=branch,
                include_global=True,
                limit=200,
            )
            by_id = {result.entry.id: result for result in results}
            for result in semantic_pool:
                by_id.setdefault(result.entry.id, result)
            results = list(by_id.values())
        candidates: list[RankedContext] = []
        for result in results:
            entry = result.entry
            semantic = self._semantic(task, entry.content)
            lexical = lexical_match(
                task,
                f"{entry.content} {entry.summary or ''} {' '.join(entry.tags)}",
            )
            confidence_feedback = (
                0.65 * result.effective_confidence
                + 0.35 * ((entry.feedback_score + 1.0) / 2.0)
            )
            breakdown = hybrid_score(
                graph_relevance=1.0 if entry.related_node_ids else None,
                semantic_similarity=semantic,
                lexical_match=lexical,
                recency_git=self._datetime_recency(entry.created_at),
                architectural_importance=None,
                test_coverage_bonus=(
                    1.0 if mode == "debug" and entry.type == MemoryType.BUG else None
                ),
                feedback_score=confidence_feedback,
                weights=weights,
            )
            content = entry.content
            summary = entry.summary
            item = ContextItem(
                kind="memory",
                content=content,
                token_estimate=estimate_tokens(content),
                score=breakdown,
                provenance=Provenance(
                    kind="memory",
                    reference=entry.id,
                    content_hash=hashlib.sha256(entry.content.encode("utf-8")).hexdigest(),
                    confidence=result.effective_confidence,
                ),
            )
            candidates.append(RankedContext(item=item, summary=summary, hierarchy=0))
        return candidates

    @staticmethod
    def _seed_nodes(
        task: str, rows: Sequence[sqlite3.Row], mode: RetrievalMode
    ) -> set[str]:
        scored = [
            (
                lexical_match(task, f"{row['name']} {row['qualname']} {row['path']}"),
                str(row["id"]),
            )
            for row in rows
        ]
        scored = [item for item in scored if item[0] > 0]
        scored.sort(key=lambda item: (-item[0], item[1]))
        limit = {"surgical": 3, "debug": 6, "exploratory": 10}[mode]
        return {node_id for _, node_id in scored[:limit]}

    @staticmethod
    def _graph_distances(
        seeds: set[str], rows: Sequence[sqlite3.Row], depth: int
    ) -> dict[str, int]:
        if not seeds:
            return {}
        adjacency: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            source = str(row["source_id"])
            target = str(row["target_id"])
            adjacency[source].add(target)
            adjacency[target].add(source)
        distances = {seed: 0 for seed in seeds}
        queue = deque(sorted(seeds))
        while queue:
            current = queue.popleft()
            if distances[current] >= depth:
                continue
            for neighbour in sorted(adjacency.get(current, ())):
                if neighbour in distances:
                    continue
                distances[neighbour] = distances[current] + 1
                queue.append(neighbour)
        return distances

    @staticmethod
    def _path_distances(
        nodes: Sequence[sqlite3.Row], distances: Mapping[str, int]
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in nodes:
            distance = distances.get(str(row["id"]))
            if distance is None:
                continue
            path = str(row["path"])
            result[path] = min(result.get(path, distance), distance)
        return result

    @staticmethod
    def _node_feedback(connection: sqlite3.Connection) -> dict[str, float]:
        rows = connection.execute(
            """
            SELECT mn.node_id, AVG(m.feedback_score) AS score
            FROM memory_nodes AS mn
            JOIN memories AS m ON m.id = mn.memory_id
            WHERE m.status = 'active'
            GROUP BY mn.node_id
            """
        ).fetchall()
        return {str(row["node_id"]): float(row["score"]) for row in rows}

    def _semantic(self, task: str, content: str) -> float | None:
        if self.semantic_scorer is None:
            return None
        try:
            value = float(self.semantic_scorer(task, content))
        except Exception:
            return None
        if not math.isfinite(value):
            return None
        return min(1.0, max(0.0, value))

    @staticmethod
    def _semantic_identity(scorer: SemanticScorer | None) -> str:
        if scorer is None:
            return "disabled"
        module = getattr(scorer, "__module__", scorer.__class__.__module__)
        name = getattr(scorer, "__qualname__", scorer.__class__.__qualname__)
        # Injected scorers without an explicit stable key are isolated per process.
        return f"{module}:{name}:{id(scorer)}"

    @staticmethod
    def _distance_score(distance: int | None, *, has_seeds: bool) -> float | None:
        if not has_seeds:
            return None
        return 0.0 if distance is None else 1.0 / (distance + 1)

    @staticmethod
    def _bounded_optional(value: object) -> float | None:
        if value is None:
            return None
        if not isinstance(value, (int, float, str)):
            return None
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return min(1.0, max(0.0, numeric))

    @staticmethod
    def _recency(mtime_ns: object, indexed_at: object) -> float | None:
        if mtime_ns is not None:
            if not isinstance(mtime_ns, (int, float, str)):
                return None
            try:
                numeric = int(mtime_ns)
            except (OverflowError, ValueError):
                numeric = 0
            if numeric > 0:
                seconds = numeric / 1_000_000_000 if numeric > 100_000_000_000_000 else numeric
                try:
                    return RetrievalEngine._datetime_recency(datetime.fromtimestamp(seconds, UTC))
                except (OSError, OverflowError, ValueError):
                    pass
        if indexed_at:
            try:
                value = datetime.fromisoformat(str(indexed_at).replace("Z", "+00:00"))
            except ValueError:
                return None
            return RetrievalEngine._datetime_recency(value)
        return None

    @staticmethod
    def _datetime_recency(value: datetime) -> float:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        elapsed = max(0.0, (utc_now() - value).total_seconds() / 86_400)
        return math.exp(-elapsed / 30.0)

    def _mode_weights(self, mode: RetrievalMode) -> dict[str, float]:
        weights = {
            key: float(value) for key, value in self.config.scoring_weights.model_dump().items()
        }
        multipliers = {
            "exploratory": {
                "graph_relevance": 1.25,
                "architectural_importance": 1.35,
            },
            "surgical": {"graph_relevance": 1.35, "lexical_match": 1.75},
            "debug": {
                "lexical_match": 1.5,
                "test_coverage_bonus": 2.5,
                "feedback_score": 1.8,
            },
        }[mode]
        for name, factor in multipliers.items():
            weights[name] *= factor
        return weights

    @staticmethod
    def _effective_depth(mode: RetrievalMode, requested: int) -> int:
        if mode == "surgical":
            return min(1, requested)
        if mode == "debug":
            return max(2, requested)
        return max(3, requested)

    @staticmethod
    def _mode_budget(mode: RetrievalMode, requested: int) -> int:
        ratio = {"exploratory": 1.0, "surgical": 0.28, "debug": 0.65}[mode]
        return max(1, min(requested, int(requested * ratio)))

    @staticmethod
    def _is_test(node_type: str, path: str) -> bool:
        normalized = path.replace("\\", "/").casefold()
        filename = normalized.rsplit("/", 1)[-1]
        return (
            node_type.casefold() == "test"
            or "/tests/" in f"/{normalized}"
            or filename.startswith("test_")
            or filename.endswith(("_test.py", ".test.ts", ".spec.ts", ".test.js", ".spec.js"))
        )

    @staticmethod
    def _chunk_summary(row: sqlite3.Row) -> str:
        qualifier = str(row["qualname"] or row["node_name"] or row["path"])
        return (
            f"{row['path']}:{row['start_line']}-{row['end_line']} "
            f"({row['node_type'] or 'code'} {qualifier})"
        )

    @staticmethod
    def _graph_summary(
        *,
        nodes: Sequence[sqlite3.Row],
        edges: Sequence[sqlite3.Row],
        seeds: set[str],
        depth: int,
        selected: Sequence[ContextItem],
    ) -> str:
        paths = sorted({item.path for item in selected if item.path})
        path_text = ", ".join(paths[:8]) if paths else "none"
        if len(paths) > 8:
            path_text += f", +{len(paths) - 8} more"
        return (
            f"Graph: {len(nodes)} nodes, {len(edges)} edges; "
            f"{len(seeds)} lexical seed(s), traversal depth {depth}; "
            f"selected paths: {path_text}."
        )


# The documented module name and the service-oriented name refer to the same API.
ContextBuilder = RetrievalEngine


def get_relevant_context(
    engine: RetrievalEngine,
    task: str,
    mode: RetrievalMode = "surgical",
    token_budget: int = 4_000,
    include_memory: bool = True,
    depth: int = 2,
) -> ContextBundle:
    """Functional facade for thin protocol adapters."""

    return engine.get_relevant_context(task, mode, token_budget, include_memory, depth)
