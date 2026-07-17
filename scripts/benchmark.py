"""Lightweight local benchmarks for ProjectMind hot paths.

Run with: ``python scripts/benchmark.py``. These timings are informational and
are excluded from functional CI gates; they help track regressions in indexing,
retrieval, and graph analysis.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from projectmind.app import AppContext


def _make_sample_project(root: Path) -> None:
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    for index in range(20):
        (root / "pkg" / f"module_{index}.py").write_text(
            f"def function_{index}():\n    return {index}\n\n"
            f"class Class{index}:\n    def method(self):\n        return function_{index}()\n",
            encoding="utf-8",
        )


def _time(label: str, callable) -> float:
    started = time.perf_counter()
    result = callable()
    elapsed = time.perf_counter() - started
    print(f"{label:<40} {elapsed * 1000:8.2f} ms")
    return elapsed


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw) / "project"
        root.mkdir()
        _make_sample_project(root)

        context = AppContext.create(root)

        _time("index_scope", lambda: context.indexer.index_scope("."))
        _time("graph.summary", lambda: context.graph.summary("."))
        _time(
            "impact_analysis",
            lambda: context.graph_analyzer.impact_analysis("pkg/module_0.py"),
        )
        _time(
            "get_relevant_context",
            lambda: context.retrieval.get_relevant_context(
                "how does function_0 work", token_budget=2000
            ),
        )
        _time(
            "detect_dependency_cycles",
            lambda: context.graph_analyzer.detect_dependency_cycles("."),
        )
        print("\nBenchmarks complete.")


if __name__ == "__main__":
    main()
