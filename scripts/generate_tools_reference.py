"""Generate ``docs/tools_reference.md`` from the live MCP tool catalog.

Run with: ``python scripts/generate_tools_reference.py``. The script builds a
temporary server instance and introspects every registered tool, emitting a
deterministic Markdown table plus per-tool argument lists.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from projectmind.server import create_server

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "tools_reference.md"


def _signature(tool_callable) -> str:
    try:
        parameters = inspect.signature(tool_callable).parameters
    except (ValueError, TypeError):
        return ""
    parts = []
    for name, param in parameters.items():
        if name in {"context", "self"}:
            continue
        annotation = "" if param.annotation is inspect.Parameter.empty else f": {param.annotation}"
        default = "" if param.default is inspect.Parameter.empty else " = ..."
        parts.append(f"{name}{annotation}{default}")
    return ", ".join(parts)


def main() -> None:
    server = create_server(REPO_ROOT)
    tool_manager = getattr(server, "_tool_manager", None)
    if tool_manager is None:
        raise RuntimeError("FastMCP tool manager is unavailable")

    tools = sorted(tool_manager._tools.items(), key=lambda item: item[0])

    lines = [
        "# ProjectMind MCP — Tool Reference",
        "",
        f"Auto-generated from `{len(tools)}` registered tools.",
        "",
        "## Catalog",
        "",
        "| Tool | Title | Read-only | Destructive |",
        "|------|-------|-----------|-------------|",
    ]
    for name, tool in tools:
        annotations = getattr(tool, "annotations", None)
        read_only = getattr(annotations, "readOnlyHint", None) or False
        destructive = getattr(annotations, "destructiveHint", None) or False
        title = getattr(tool, "title", name) or name
        lines.append(f"| `{name}` | {title} | {read_only} | {destructive} |")

    lines.append("")
    lines.append("## Details")
    lines.append("")
    for name, tool in tools:
        title = getattr(tool, "title", name) or name
        doc = (tool.fn.__doc__ or "").strip() if hasattr(tool, "fn") else ""
        lines.append(f"### `{name}` — {title}")
        if doc:
            lines.append("")
            lines.append(doc)
        lines.append("")
        lines.append(f"```python")
        lines.append(f"{name}({_signature(tool.fn)})")
        lines.append("```")
        lines.append("")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len(tools)} tools)")


if __name__ == "__main__":
    main()
