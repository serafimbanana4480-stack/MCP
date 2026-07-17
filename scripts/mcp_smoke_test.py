"""Exercise every registered ProjectMind MCP tool against an isolated fixture.

This is intentionally a protocol-level smoke test rather than a unit test: it
uses the official SDK client/server connection and reports both successful
calls and expected confirmation/capability failures.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from projectmind.server import create_server


def _content(result: object) -> object:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    return [getattr(item, "text", repr(item)) for item in getattr(result, "content", [])]


async def _run() -> int:
    with tempfile.TemporaryDirectory(
        prefix="projectmind-smoke-", ignore_cleanup_errors=True
    ) as raw_root:
        root = Path(raw_root)
        (root / "main.py").write_text(
            "from helpers import add\n\n\ndef calculate(value: int) -> int:\n"
            "    return add(value, 1)\n",
            encoding="utf-8",
        )
        (root / "helpers.py").write_text(
            "def add(left: int, right: int) -> int:\n    return left + right\n",
            encoding="utf-8",
        )
        (root / "tests").mkdir()
        (root / "tests" / "test_main.py").write_text(
            "from main import calculate\n\n\ndef test_calculate():\n    assert calculate(1) == 2\n",
            encoding="utf-8",
        )

        server = create_server(root)
        async with create_connected_server_and_client_session(
            server, raise_exceptions=False
        ) as session:
            listing = await session.list_tools()
            tool_names = [tool.name for tool in listing.tools]
            called: set[str] = set()
            print(json.dumps({"registered_count": len(tool_names), "tools": tool_names}))

            async def call(name: str, arguments: dict[str, object]) -> object:
                called.add(name)
                result = await session.call_tool(name, arguments)
                payload = _content(result)
                print(
                    json.dumps(
                        {
                            "tool": name,
                            "is_error": result.isError,
                            "payload": payload,
                        },
                        default=str,
                    )[:2000]
                )
                return payload

            await call("ping", {})
            await call("get_capabilities", {})
            await call("status", {})
            proposal = await call(
                "propose_edit",
                {
                    "target": "helpers.py",
                    "patch": "def add(left: int, right: int) -> int:\n"
                    "    return left + right + 0\n",
                    "patch_format": "auto",
                },
            )
            if isinstance(proposal, dict):
                await call(
                    "confirm_and_apply",
                    {
                        "patch_id": proposal.get("patch_id", ""),
                        "proposal_digest": proposal.get("proposal_digest", ""),
                        "confirm": True,
                    },
                )
            await call("run_command_sandboxed", {"command": ["pytest", "-q"], "confirm": True})
            await call("scan_secrets", {})
            await call("scan_owasp", {})
            await call("get_usage_stats", {})
            await call("self_improvement_report", {})
            await call("index_scope", {})
            await call("reindex_on_git_pull", {})
            await call("get_graph_summary", {})

            with sqlite3.connect(root / ".projectmind" / "projectmind.db") as db:
                node_id = db.execute("SELECT id FROM nodes ORDER BY id LIMIT 1").fetchone()[0]
            await call("find_critical_files", {})
            await call("detect_dependency_cycles", {})
            await call("detect_code_smells", {})
            await call("suggest_refactoring", {"node_id": node_id})
            await call("impact_analysis", {"node_id_or_diff": node_id})
            await call("parallel_impact_analysis", {"changes": [node_id]})
            await call("export_diagram", {})
            await call("simulate_change", {"proposed_change": "change calculate"})

            first_memory = await call(
                "record_decision",
                {"content": "Use local SQLite for durable project memory", "tags": ["storage"]},
            )
            await call(
                "record_decision",
                {"content": "Keep SQLite as the durable memory store", "tags": ["storage"]},
            )
            await call(
                "record_learning",
                {"outcome": "The indexed graph made impact analysis faster", "tags": ["storage"]},
            )
            search = await call("memory_search", {"query": "SQLite memory"})
            await call("consolidate_memory", {"min_cluster_size": 2})
            if isinstance(search, list) and search:
                memory_id = search[0].get("entry", {}).get("id", "")
            elif isinstance(first_memory, dict):
                memory_id = first_memory.get("id", "")
            else:
                memory_id = ""
            await call("feedback_thumbs_up", {"memory_id": memory_id})
            await call("feedback_thumbs_down", {"memory_id": memory_id})
            await call("export_memory", {"path": "memory-export.json"})
            await call("import_memory", {"path": "memory-export.json", "conflict": "skip"})
            await call("verify_memory", {"memory_id": memory_id})
            await call("get_relevant_context", {"task": "change calculate"})
            await call("find_similar_past_solutions", {"task_description": "change calculate"})

            sequential = await call("sequential_think", {"task": "change calculate"})
            if isinstance(sequential, dict):
                steps = sequential.get("steps", [])
                if steps:
                    await call(
                        "validate_step",
                        {"step_id": steps[0]["id"], "evidence": "fixture checked"},
                    )
            await call("react_step", {"task_id": "smoke-task", "current_thought": "inspect graph"})
            await call("explore_alternatives", {"task": "change calculate"})
            await call("self_reflect", {"output": "The change is safe", "criteria": "evidence"})
            if isinstance(sequential, dict):
                await call("critique_plan", {"plan_id": sequential.get("id", "")})
            await call(
                "critique_code_change",
                {"diff": "-return add(value, 1)\n+return add(value, 2)\n"},
            )
            await call("play_devils_advocate", {"proposal": "Change the calculation"})
            await call(
                "confidence_score", {"response": "The change is safe", "context": "tests pass"}
            )
            hierarchical = await call("hierarchical_planning", {"goal": "change calculate"})
            if isinstance(hierarchical, dict):
                await call("risk_assessment_matrix", {"plan_id": hierarchical.get("plan_id", "")})
            long_task = await call("create_long_running_task", {"spec": "change calculate"})
            if isinstance(long_task, dict):
                await call("resume_task", {"task_id": long_task.get("id", "")})
            await call(
                "compare_implementations",
                {"option_a": "local", "option_b": "remote", "criteria": ["safety"]},
            )
            await call("generate_boilerplate", {"pattern": "service", "pattern_context": "Python"})
            await call("detect_related_bugs", {"description": "calculation error"})
            await call("root_cause_analysis", {"error": "AssertionError in test_calculate"})
            await call(
                "reproduce_issue", {"description": "calculation error", "error": "AssertionError"}
            )
            await call("run_mutation_testing", {"scope": ".", "confirm": False})
            await call("run_linters", {"scope": ".", "confirm": False})
            await call(
                "regression_analysis",
                {"fix_diff": "-return add(value, 1)\n+return add(value, 2)\n", "confirm": False},
            )
            await call("update_docs", {})

            missing = sorted(set(tool_names) - called)
            print(
                json.dumps(
                    {"completed": True, "registered_count": len(tool_names), "missing": missing}
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
