from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from projectmind.config import MemoryConfig, ScoringWeights
from projectmind.database import Database
from projectmind.errors import ConflictError, NotFoundError, SecurityError
from projectmind.memory import MemoryStore, feedback_thumbs_down, feedback_thumbs_up
from projectmind.memory.consolidation import DeterministicConsolidator
from projectmind.memory.store import effective_confidence
from projectmind.models.common import Provenance
from projectmind.models.memory_models import MemoryEntry, MemoryType
from projectmind.models.retrieval_models import ContextBundle, ContextItem, ScoreBreakdown
from projectmind.retrieval import RetrievalEngine, hybrid_score, renormalized_score
from projectmind.retrieval.cache import ContextCache
from projectmind.retrieval.hierarchical_rag import (
    RankedContext,
    estimate_tokens,
    fit_context_to_budget,
    truncate_to_tokens,
)
from projectmind.retrieval.scoring import lexical_match


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / ".projectmind" / "projectmind.db", tmp_path)
    database.initialize()
    return database


def test_memory_crud_persists_relations_and_soft_delete(database: Database) -> None:
    store = MemoryStore(database)
    created = store.create(
        "Use repository interfaces around SQLite.",
        memory_type=MemoryType.DECISION,
        tags=["architecture", "sqlite", "architecture"],
        related_node_ids=["node_repo"],
        branch="feature/memory",
    )

    restarted = MemoryStore(database)
    loaded = restarted.get(created.id)
    assert loaded.tags == ["architecture", "sqlite"]
    assert loaded.related_node_ids == ["node_repo"]

    updated = restarted.update(created.id, summary="Repository boundary", confidence=0.9)
    assert updated.summary == "Repository boundary"
    assert restarted.delete(created.id)
    with pytest.raises(NotFoundError):
        restarted.get(created.id)
    assert restarted.get(created.id, include_deleted=True).status == "deleted"
    assert not restarted.delete("mem_missing")


def test_branch_search_confidence_ageing_feedback_and_verify(database: Database) -> None:
    config = MemoryConfig(half_life_days_decision=10, half_life_days_debug_note=2)
    store = MemoryStore(database, config)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    feature = store.create(
        "Authentication tokens are rotated after login.",
        memory_type="decision",
        branch="feature/auth",
        confidence=0.8,
        created_at=old,
    )
    global_memory = store.create(
        "Authentication uses short lived access tokens.",
        memory_type="decision",
        branch="main",
        confidence=0.8,
        created_at=old,
    )
    store.create(
        "Payments use idempotency keys.",
        memory_type="decision",
        branch="feature/payments",
        created_at=old,
    )

    now = old + timedelta(days=10)
    results = store.search("authentication tokens", current_branch="feature/auth", now=now)
    assert {result.entry.id for result in results} == {feature.id, global_memory.id}
    assert all(result.effective_confidence == pytest.approx(0.4) for result in results)

    boosted = store.feedback_thumbs_up(feature.id)
    assert boosted.feedback_score == pytest.approx(0.1)
    refreshed = store.verify(feature.id, at=now)
    assert refreshed.confidence == refreshed.initial_confidence
    assert store.aged_confidence(refreshed, now=now) == pytest.approx(0.8)
    scoped = MemoryStore(database, config, current_branch="feature/auth")
    automatic = scoped.create("Authentication audit events are retained.")
    assert automatic.branch == "feature/auth"
    assert scoped.search("audit events")[0].entry.id == automatic.id
    with pytest.raises(ValueError):
        MemoryStore(
            database,
            current_branch="feature/auth",
            branch_resolver=lambda: "feature/auth",
        )


def test_memory_validation_crud_filters_and_feedback_facades(database: Database) -> None:
    store = MemoryStore(database)
    naive = datetime(2026, 1, 1)
    entry = MemoryEntry(
        id="mem_manual",
        type=MemoryType.CONVENTION,
        content="  Keep adapters typed.  ",
        summary="  Typed adapter  ",
        tags=["typing", "typing"],
        related_node_ids=["node_adapter", "node_adapter"],
        confidence=0.6,
        initial_confidence=0.6,
        created_at=naive,
        source=" test ",
    )
    created = store.create(entry)
    assert created.content == "Keep adapters typed."
    assert created.source == "test"
    assert created.tags == ["typing"]
    assert effective_confidence(
        created, now=naive + timedelta(days=30), half_life_days=30
    ) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        effective_confidence(created, half_life_days=0)
    with pytest.raises(ValueError):
        store.create(" ")
    with pytest.raises(ConflictError):
        store.create(created)

    lesson = store.record_learning(
        "Shipped",
        what_went_well="Small commits",
        what_failed="Slow fixture",
        lessons="Prefer focused fixtures",
        tags=["testing"],
    )
    assert "Lessons: Prefer focused fixtures" in lesson.content
    assert store.list_entries(memory_type="lesson", limit=1) == [lesson]
    with pytest.raises(ValueError):
        store.list_entries(limit=-1)
    with pytest.raises(NotFoundError):
        store.update("mem_missing", summary="missing")
    with pytest.raises(ValueError):
        store.update(created.id, id="replacement")
    with pytest.raises(ValueError):
        store.update(created.id, branch=42)
    with pytest.raises(ValueError):
        store.update(created.id, tags="not-a-list")

    reassessed = store.update(created.id, confidence=0.9, related_node_ids=["node_new"])
    assert reassessed.initial_confidence == pytest.approx(0.9)
    assert reassessed.related_node_ids == ["node_new"]
    assert store.feedback(created.id, "up").feedback_score == pytest.approx(0.1)
    assert store.feedback(created.id, positive=False).feedback_score == pytest.approx(0.0)
    assert store.feedback(created.id, True).feedback_score == pytest.approx(0.1)
    assert feedback_thumbs_up(store, created.id).feedback_score == pytest.approx(0.2)
    assert feedback_thumbs_down(store, created.id).feedback_score == pytest.approx(0.1)
    with pytest.raises(ValueError):
        store.feedback(created.id)
    with pytest.raises(ValueError):
        store.feedback(created.id, "up", positive=True)
    with pytest.raises(ValueError):
        store.apply_feedback(created.id, positive=True, step=0)

    assert store.search("", tags=["typing"], include_global=False)[0].entry.id == created.id
    assert store.search("typed", min_confidence=1.0) == []
    with pytest.raises(ValueError):
        store.search("typed", min_confidence=2)
    with pytest.raises(ValueError):
        store.search("typed", limit=-1)
    with pytest.raises(ValueError):
        store.search("typed", memory_type="lesson", type="bug")
    assert store.delete(created.id, hard=True)
    with pytest.raises(NotFoundError):
        store.get(created.id, include_deleted=True)


def test_json_round_trip_is_confined_to_authorized_root(
    database: Database, tmp_path: Path
) -> None:
    store = MemoryStore(database, io_root=tmp_path / "exchange")
    entry = store.record_decision("Prefer deterministic local fallbacks.", tags=["local-first"])
    exported = store.export_json("team/memory.json")
    assert exported.is_file()

    other_root = tmp_path / "other"
    other = Database(other_root / ".projectmind" / "projectmind.db", other_root)
    other.initialize()
    imported_store = MemoryStore(other, io_root=tmp_path / "exchange")
    imported = imported_store.import_json(exported)
    assert [item.id for item in imported] == [entry.id]
    assert imported_store.get(entry.id).tags == ["local-first"]

    with pytest.raises(SecurityError):
        store.export_json("../escaped.json")
    with pytest.raises(SecurityError):
        store.import_json(tmp_path / "outside.json")


def test_import_validates_conflicts_forward_references_and_cycles(
    database: Database, tmp_path: Path
) -> None:
    io_root = tmp_path / "io"
    io_root.mkdir()
    store = MemoryStore(database, io_root=io_root)
    target = MemoryEntry(
        id="mem_new",
        type=MemoryType.LESSON,
        content="Consolidated lesson",
        confidence=0.8,
        initial_confidence=0.8,
    )
    original = MemoryEntry(
        id="mem_old",
        type=MemoryType.LESSON,
        content="Original lesson",
        confidence=0.7,
        initial_confidence=0.7,
        superseded_by=target.id,
        status="superseded",
    )

    def write_payload(name: str, entries: list[dict[str, object]]) -> Path:
        path = io_root / name
        path.write_text(
            json.dumps(
                {
                    "schema": "projectmind-memory",
                    "schema_version": 1,
                    "memories": entries,
                }
            ),
            encoding="utf-8",
        )
        return path

    forward = write_payload(
        "forward.json",
        [original.model_dump(mode="json"), target.model_dump(mode="json")],
    )
    assert {entry.id for entry in store.import_json(forward)} == {"mem_old", "mem_new"}
    assert store.get("mem_old").superseded_by == "mem_new"
    assert store.import_json(forward) == []
    with pytest.raises(ConflictError):
        store.import_json(forward, conflict="error")
    target.content = "Replacement consolidated lesson"
    replacement = write_payload("replace.json", [target.model_dump(mode="json")])
    store.import_json(replacement, conflict="replace")
    assert store.get(target.id).content.startswith("Replacement")

    left = original.model_copy(update={"id": "mem_left", "superseded_by": "mem_right"})
    right = original.model_copy(update={"id": "mem_right", "superseded_by": "mem_left"})
    cycle = write_payload(
        "cycle.json", [left.model_dump(mode="json"), right.model_dump(mode="json")]
    )
    with pytest.raises(ValueError, match="cycle"):
        store.import_json(cycle)
    dangling = write_payload(
        "dangling.json",
        [left.model_copy(update={"superseded_by": "mem_absent"}).model_dump(mode="json")],
    )
    with pytest.raises(ValueError, match="dangling"):
        store.import_json(dangling)
    with pytest.raises(ValueError):
        store.import_json(forward, conflict="overwrite")  # type: ignore[arg-type]

    invalid = io_root / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid memory JSON"):
        store.import_json(invalid)
    wrong_schema = write_payload("wrong.json", [])
    raw = json.loads(wrong_schema.read_text(encoding="utf-8"))
    raw["schema"] = "unknown"
    wrong_schema.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        store.import_json(wrong_schema)
    with pytest.raises(SecurityError):
        store.export_json(io_root)
    with pytest.raises(NotFoundError):
        store.import_json("missing.json")


class _SummaryAdapter:
    def consolidate(self, entries: tuple[MemoryEntry, ...]) -> str:
        assert [entry.id for entry in entries] == sorted(entry.id for entry in entries)
        return "Keep database access behind one repository boundary."


def test_consolidation_is_deterministic_traceable_and_has_optional_boundary(
    database: Database,
) -> None:
    store = MemoryStore(database)
    originals = [
        store.create(
            text,
            memory_type="convention",
            tags=["repository"],
            memory_id=f"mem_{index}",
        )
        for index, text in enumerate(
            [
                "Database access belongs in repositories.",
                "Services call repository interfaces.",
                "Tests replace repositories with fakes.",
            ]
        )
    ]

    result = DeterministicConsolidator(store, adapter=_SummaryAdapter()).consolidate()
    assert result.capability_mode == "llm_enhanced"
    assert len(result.consolidated) == 1
    assert result.consolidated[0].content.startswith("Keep database access")
    assert result.superseded_ids == [entry.id for entry in originals]
    assert [entry.id for entry in store.sources_for(result.consolidated[0].id)] == [
        entry.id for entry in originals
    ]
    for original in originals:
        persisted = store.get(original.id)
        assert persisted.status == "superseded"
        assert persisted.superseded_by == result.consolidated[0].id

    # Re-running has no active source cluster and therefore cannot duplicate knowledge.
    repeated = store.consolidate(min_cluster_size=3)
    assert repeated.consolidated == []


def test_consolidation_fallback_keeps_branches_isolated(database: Database) -> None:
    store = MemoryStore(database)
    for branch in ("feature/a", "feature/b"):
        for index in range(2):
            store.create(
                f"Repository convention {branch} {index}",
                memory_type="convention",
                tags=["repository"],
                branch=branch,
            )

    class FailingAdapter:
        def consolidate(self, entries: tuple[MemoryEntry, ...]) -> str:
            raise RuntimeError("adapter unavailable")

    result = DeterministicConsolidator(
        store, adapter=FailingAdapter(), min_cluster_size=2
    ).consolidate()
    assert result.capability_mode == "deterministic"
    assert {entry.branch for entry in result.consolidated} == {"feature/a", "feature/b"}
    assert all(entry.content.startswith("Consolidated knowledge") for entry in result.consolidated)
    with pytest.raises(ValueError):
        DeterministicConsolidator(store, min_cluster_size=1)
    with pytest.raises(ValueError):
        DeterministicConsolidator(store, lexical_threshold=2)
    with pytest.raises(TypeError):
        store.consolidate(adapter=object())


def test_scoring_renormalizes_only_unavailable_signals() -> None:
    weights = ScoringWeights()
    without_semantic = renormalized_score(
        {
            "graph_relevance": 1.0,
            "semantic_similarity": None,
            "lexical_match": 0.0,
            "recency_git": None,
            "architectural_importance": None,
            "test_coverage_bonus": None,
            "feedback_score": None,
        },
        weights,
    )
    assert without_semantic == pytest.approx(0.30 / (0.30 + 0.15))
    breakdown = hybrid_score(graph_relevance=1.0, lexical_match=0.0, weights=weights)
    assert breakdown.semantic_similarity is None
    assert breakdown.final_score == pytest.approx(without_semantic)

    with pytest.raises(ValueError):
        renormalized_score({"graph_relevance": 1.1})

    assert renormalized_score({}) == 0
    assert lexical_match("", "anything") == 0
    assert lexical_match("missing", "anything") == 0
    assert lexical_match("auth token", "Auth token validation") == 1
    with pytest.raises(ValueError):
        renormalized_score({"graph_relevance": 1}, {"graph_relevance": -1})
    with pytest.raises(ValueError):
        renormalized_score({"graph_relevance": math.nan})


def test_hierarchical_budget_and_revision_cache(database: Database) -> None:
    score = ScoreBreakdown(lexical_match=1, final_score=1)
    first = ContextItem(
        kind="code",
        content="alpha " * 80,
        path="alpha.py",
        token_estimate=80,
        score=score,
        provenance=Provenance(kind="chunk", reference="chunk_alpha"),
    )
    duplicate = first.model_copy(update={"content": "duplicate"})
    second = ContextItem(
        kind="graph",
        content="beta node",
        token_estimate=2,
        score=score.model_copy(update={"final_score": 0.5}),
        provenance=Provenance(kind="node", reference="node_beta"),
    )
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") >= 1
    assert estimate_tokens(truncate_to_tokens(first.content, 10)) <= 10
    fitted, used = fit_context_to_budget(
        [
            RankedContext(first, summary="alpha summary"),
            RankedContext(duplicate),
            RankedContext(second),
        ],
        10,
        minimum_item_tokens=1,
    )
    assert fitted[0].content == "alpha summary"
    assert used <= 10
    assert fit_context_to_budget([], 0) == ([], 0)
    with pytest.raises(ValueError):
        fit_context_to_budget([], -1)

    bundle = ContextBundle(
        task="alpha",
        mode="surgical",
        items=fitted,
        graph_summary="graph",
        tokens_used=used,
        token_budget=10,
    )
    cache = ContextCache(database)
    key = cache.key(
        " Alpha ", mode="surgical", token_budget=10, include_memory=False, depth=1
    )
    assert key == cache.key(
        "alpha", mode="surgical", token_budget=10, include_memory=False, depth=1
    )
    assert cache.get(key) is None
    cache.put(key, bundle)
    assert cache.get(key).cache_hit  # type: ignore[union-attr]
    with database.transaction(immediate=True) as connection:
        Database.bump_index_revision(connection)
    assert cache.get(key) is None
    assert cache.prune_stale() == 1
    cache.put(key, bundle)
    assert cache.delete(key)
    assert not cache.delete(key)


def _seed_index(database: Database) -> None:
    now_ns = int(datetime.now(UTC).timestamp() * 1_000_000_000)
    files = [
        ("src/auth.py", "python", "auth-hash"),
        ("src/service.py", "python", "service-hash"),
        ("tests/test_auth.py", "python", "test-hash"),
    ]
    nodes = [
        ("node_auth", "function", "authenticate", "auth.authenticate", "src/auth.py", 0.8, 0.7),
        ("node_service", "class", "AuthService", "service.AuthService", "src/service.py", 0.9, 0.5),
        ("node_test", "test", "test_auth", "test_auth.test_auth", "tests/test_auth.py", 0.2, 1.0),
    ]
    with database.transaction(immediate=True) as connection:
        connection.executemany(
            """
            INSERT INTO files(path, language, content_hash, mtime_ns, size_bytes)
            VALUES (?, ?, ?, ?, 100)
            """,
            [(path, language, digest, now_ns) for path, language, digest in files],
        )
        connection.executemany(
            """
            INSERT INTO nodes(
                id, type, name, qualname, path, start_line, end_line, language,
                centrality, test_coverage
            ) VALUES (?, ?, ?, ?, ?, 1, 20, 'python', ?, ?)
            """,
            nodes,
        )
        connection.executemany(
            """
            INSERT INTO chunks(
                id, path, node_id, start_line, end_line, content, content_hash,
                token_estimate, summary
            ) VALUES (?, ?, ?, 1, 20, ?, ?, 80, ?)
            """,
            [
                (
                    "chunk_auth",
                    "src/auth.py",
                    "node_auth",
                    "def authenticate(token):\n    return verify_signature(token)\n" * 8,
                    "chunk-auth-hash",
                    "Validates an authentication token signature.",
                ),
                (
                    "chunk_service",
                    "src/service.py",
                    "node_service",
                    (
                        "class AuthService:\n"
                        "    def login(self, token): return authenticate(token)\n"
                    )
                    * 8,
                    "chunk-service-hash",
                    "Coordinates the authentication login flow.",
                ),
                (
                    "chunk_test",
                    "tests/test_auth.py",
                    "node_test",
                    "def test_auth_rejects_bad_signature(): assert not authenticate('bad')\n" * 8,
                    "chunk-test-hash",
                    "Regression test for invalid authentication signatures.",
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO edges(source_id, target_id, type) VALUES (?, ?, ?)",
            [
                ("node_service", "node_auth", "calls"),
                ("node_test", "node_auth", "tests"),
            ],
        )
        Database.bump_index_revision(connection)


def test_context_modes_budget_cache_invalidation_and_provenance(database: Database) -> None:
    _seed_index(database)
    store = MemoryStore(database)
    bug = store.create(
        "Invalid authentication signatures once bypassed validation.",
        memory_type="bug",
        tags=["auth"],
        related_node_ids=["node_auth"],
        branch="main",
    )
    engine = RetrievalEngine(database, store)

    exploratory = engine.get_relevant_context(
        "debug authentication signature", "exploratory", 500, True, 2
    )
    surgical = engine.get_relevant_context(
        "debug authentication signature", "surgical", 500, True, 2
    )
    debug = engine.get_relevant_context("debug authentication signature", "debug", 500, True, 2)

    assert exploratory.tokens_used <= 500
    assert surgical.tokens_used <= 140
    assert surgical.tokens_used < exploratory.tokens_used * 0.30
    assert all(item.provenance.reference for item in exploratory.items)
    assert any(item.provenance.reference == bug.id for item in debug.items)
    assert any(item.path == "tests/test_auth.py" for item in debug.items)

    cached = engine.get_relevant_context(
        "debug authentication signature", "exploratory", 500, True, 2
    )
    assert cached.cache_hit
    store.feedback_thumbs_up(bug.id)
    invalidated = engine.get_relevant_context(
        "debug authentication signature", "exploratory", 500, True, 2
    )
    assert not invalidated.cache_hit


def test_retrieval_validation_empty_index_and_semantic_memory_pool(database: Database) -> None:
    store = MemoryStore(database)
    semantic_only = store.create(
        "The message broker queue drains through a dedicated worker.",
        memory_type="lesson",
        branch="main",
    )
    matching_bug = store.create(
        "Delivery latency was caused by a stalled broker consumer.",
        memory_type="bug",
        branch="main",
    )

    def semantic_scorer(task: str, content: str) -> float:
        del task
        return 1.0 if "queue drains" in content else 0.0

    engine = RetrievalEngine(
        database,
        store,
        semantic_scorer=semantic_scorer,
        semantic_cache_key="test-semantic-v1",
    )
    semantic = engine.get_relevant_context(
        "throughput bottleneck", "surgical", 200, True, 0
    )
    assert any(item.provenance.reference == semantic_only.id for item in semantic.items)
    assert "No indexed code chunks" in " ".join(semantic.warnings)
    assert "Semantic similarity unavailable" not in " ".join(semantic.warnings)
    assert engine.get_relevant_context(
        "throughput bottleneck", "surgical", 200, True, 0
    ).cache_hit
    assert engine.find_similar_past_solutions("delivery latency")[0].entry.id == matching_bug.id

    without_memory = engine.get_relevant_context(
        "throughput bottleneck", "exploratory", 100, False, 0
    )
    assert without_memory.items == []
    failing = RetrievalEngine(
        database,
        store,
        semantic_scorer=lambda _task, _content: math.nan,
        semantic_cache_key="failing-semantic",
    ).get_relevant_context("unmatched terms", "exploratory", 100, True, 1)
    assert "Semantic similarity unavailable" in " ".join(failing.warnings)

    with pytest.raises(ValueError):
        engine.get_relevant_context(" ")
    with pytest.raises(ValueError):
        engine.get_relevant_context("task", "wide")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        engine.get_relevant_context("task", token_budget=0)
    with pytest.raises(ValueError):
        engine.get_relevant_context("task", depth=-1)
