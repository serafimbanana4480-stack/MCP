from .ranking import rank_file
from .task_cache import get_or_none, put
from .token_budget import trim_to_budget


def retrieve(db, task: str, token_budget: int, weights: dict, mode: str = "exploratory") -> dict:
    cached = get_or_none(db, task)
    if cached:
        return {**cached, "cache_hit": True}
    rows = db.rows("SELECT * FROM files")
    ranked = [
        rank_file(task, row, importance=1 if row.get("is_test") == 0 else 0.4, weights=weights)
        for row in rows
    ]
    if mode == "surgical":
        ranked = [x for x in ranked if x["relevance"] > 0.05]
    selected = trim_to_budget(ranked, token_budget)
    symbols = []
    for row in selected:
        symbols.extend(
            db.rows(
                "SELECT name,qualified_name,kind,start_line,end_line,file_id FROM symbols WHERE file_id=?",
                (row["id"],),
            )
        )
    result = {
        "summary": f"Contexto recuperado para: {task}",
        "files": selected,
        "symbols": symbols,
        "memories": [],
        "tests": [x for x in selected if x.get("is_test")],
        "risks": [],
        "next_steps": ["consultar impact_analysis", "criar plano validado"],
        "cache_hit": False,
    }
    put(db, task, result)
    return result
