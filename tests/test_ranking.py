from projectmind.retrieval.ranking import lexical_score, rank_file


def test_hybrid_ranking_has_explicit_breakdown():
    assert lexical_score("auth login", "src/auth.py login") > 0
    item = rank_file("auth", {"path": "src/auth.py", "content": "auth"})
    assert set(item["scoring_breakdown"]) == {
        "graph_relevance",
        "semantic_similarity",
        "lexical_match",
        "recency_git",
        "architectural_importance",
    }
