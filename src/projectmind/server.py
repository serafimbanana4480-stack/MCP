from __future__ import annotations

import argparse
import inspect
import json
from typing import Any

from .application import ProjectMind
from .core.config import Config

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - allows CLI diagnostics before dependencies are installed
    FastMCP = None  # type: ignore[assignment,misc]


TOOL_NAMES = [
    "project_scan",
    "project_summary",
    "find_symbol",
    "get_file_overview",
    "get_relevant_context",
    "impact_analysis",
    "trace_request_flow",
    "critical_files",
    "detect_smells",
    "suggest_refactoring",
    "simulate_change",
    "export_diagram",
    "memory_search",
    "record_decision",
    "record_attempt",
    "consolidate_memory",
    "memory_feedback",
    "set_branch_memory",
    "export_memory",
    "import_memory",
    "propose_edit",
    "confirm_and_apply",
    "run_in_sandbox",
    "create_plan",
    "hierarchical_planning",
    "validate_plan",
    "challenge_plan",
    "check_completion",
    "create_long_running_task",
    "parallel_impact_analysis",
    "compare_implementations",
    "generate_boilerplate",
    "debug_start",
    "collect_evidence",
    "root_cause_analysis",
    "generate_hypotheses",
    "hypothesis_testing_loop",
    "verify_fix",
    "detect_related_bugs",
    "reproduce_issue",
    "generate_tests",
    "mutation_testing",
    "static_analysis",
    "analyze_regression",
    "scan_secrets",
    "update_docs",
    "self_improve",
    "sequential_think",
    "react_step",
    "explore_alternatives",
    "self_reflect",
    "critique_code_change",
    "risk_assessment_matrix",
    "play_devils_advocate",
    "cognitive_force",
    "response_confidence",
    "record_learning",
    "find_similar_past_solutions",
    "validate_step",
    "usage_dashboard_data",
]


def create_server(root: str = "."):
    if FastMCP is None:
        raise RuntimeError("Instale as dependências com: pip install -e .")
    app = ProjectMind(root)
    mcp = FastMCP("ProjectMind")

    for name in TOOL_NAMES:

        def make_tool(tool_name: str):
            def tool(*args: Any, **kwargs: Any) -> dict[str, Any]:
                """Invoke a ProjectMind tool using its named contract."""
                return app.call(tool_name, kwargs)

            tool.__name__ = tool_name
            tool.__signature__ = inspect.signature(getattr(app, f"tool_{tool_name}"))  # type: ignore[attr-defined]
            tool.__doc__ = f"ProjectMind tool: {tool_name}."
            return tool

        mcp.tool(name=name)(make_tool(name))

    @mcp.resource("resource://project/summary")
    def project_summary_resource() -> str:
        return json.dumps(app.summary(), ensure_ascii=False, default=str)

    @mcp.resource("resource://graph/export")
    def graph_export_resource() -> str:
        return app.graph.export("json")

    @mcp.resource("resource://usage/dashboard")
    def usage_dashboard_resource() -> str:
        import json
        return json.dumps(app.tool_usage_dashboard_data(), default=str)

    @mcp.resource("resource://memory/digest")
    def memory_digest_resource() -> str:
        return json.dumps(
            {
                "active_memories": app.db.rows(
                    "SELECT * FROM memories WHERE status='active' ORDER BY updated_at DESC LIMIT 20"
                ),
                "recent_decisions": app.memory.search("", type="decision", limit=10),
            },
            ensure_ascii=False,
            default=str,
        )

    prompts = {
        "systematic_debug": "Executa debug_start → collect_evidence → generate_hypotheses → verify_fix.",
        "verified_planning": "Executa create_plan → validate_plan → challenge_plan → check_completion.",
        "structured_reasoning": "Executa sequential_think → explore_alternatives → self_reflect → critique_code_change → record_learning.",
        "evidence_debug_loop": "Estende systematic_debug com react_step e hypothesis_testing_loop.",
    }
    for name, text in prompts.items():

        def make_prompt(prompt_text: str):
            def prompt() -> str:
                return prompt_text

            return prompt

        mcp.prompt(name=name)(make_prompt(text))

    @mcp.prompt("usage_review")
    def usage_review_prompt() -> str:
        return (
            "Revise as métricas de usage do ProjectMind (resource://usage/dashboard): "
            "tokens de input/output, tokens poupados por cache, custo estimado em USD, "
            "e quais ações consomem mais contexto. Sugira otimizações de retrieval."
        )
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="projectmind")
    parser.add_argument("--root", default=".")
    parser.add_argument("command", nargs="?", default="serve")
    parser.add_argument("rest", nargs="*")
    args = parser.parse_args()
    app = ProjectMind(args.root)
    if args.command == "serve":
        create_server(args.root).run(transport="stdio")
    elif args.command in {"status", "summary"}:
        print(json.dumps(app.summary(), indent=2, ensure_ascii=False, default=str))
    elif args.command == "index":
        scope = args.rest[0] if args.rest else None
        print(json.dumps(app.tool_project_scan(scope=scope), indent=2, ensure_ascii=False))
    elif args.command == "memory":
        query = " ".join(args.rest[1:]) if args.rest and args.rest[0] == "search" else ""
        print(json.dumps(app.tool_memory_search(query=query), indent=2, ensure_ascii=False))
    elif args.command == "graph":
        fmt = "mermaid" if "export" in args.rest else "json"
        print(app.tool_export_diagram(format=fmt)["diagram"])
    elif args.command == "docs":
        print(json.dumps(app.tool_update_docs(), indent=2, ensure_ascii=False))
    elif args.command == "telemetry":
        print(
            json.dumps(
                {
                    "events": app.db.rows(
                        "SELECT * FROM telemetry ORDER BY created_at DESC LIMIT 100"
                    )
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif args.command == "dashboard":
        from .dashboard.app import run_dashboard
        run_dashboard(
            root=str(Config.load(args.root).root) if hasattr(args, "root") else ".",
            host="127.0.0.1",
            port=8777,
        )
        return
    else:
        parser.error(f"comando desconhecido: {args.command}")


if __name__ == "__main__":
    main()
