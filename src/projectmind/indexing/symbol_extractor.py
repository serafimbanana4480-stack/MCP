from __future__ import annotations

import ast
import re
from pathlib import Path

EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".sql": "sql",
}


def language_for(path: Path) -> str:
    return EXTENSIONS.get(path.suffix.lower(), path.suffix.lstrip(".") or "text")


def extract_symbols(path: Path, content: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if path.suffix == ".py":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    result.append(
                        {
                            "name": node.name,
                            "qualified_name": node.name,
                            "kind": kind,
                            "start_line": node.lineno,
                            "end_line": getattr(node, "end_lineno", node.lineno),
                            "signature": ast.unparse(node.args) if hasattr(node, "args") else "",
                            "docstring": ast.get_docstring(node) or "",
                            "complexity": 1
                            + sum(
                                isinstance(x, (ast.If, ast.For, ast.While, ast.BoolOp, ast.Try))
                                for x in ast.walk(node)
                            ),
                        }
                    )
            return result
        except SyntaxError:
            pass
    pattern = re.compile(
        r"(?m)^\s*(?:export\s+)?(?:(?:async|public|private|static)\s+)*(class|function|def|fn|func|interface|type)\s+([A-Za-z_$][\w$]*)"
    )
    for match in pattern.finditer(content):
        line = content.count("\n", 0, match.start()) + 1
        result.append(
            {
                "name": match.group(2),
                "qualified_name": match.group(2),
                "kind": match.group(1),
                "start_line": line,
                "end_line": line,
                "signature": match.group(0).strip(),
                "docstring": "",
                "complexity": 1,
            }
        )
    return result
