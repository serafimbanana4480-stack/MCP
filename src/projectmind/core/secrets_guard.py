from __future__ import annotations

import re

PATTERNS = {
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "aws_key": r"\bAKIA[0-9A-Z]{16}\b",
    "generic_secret": r"(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*[\"']?[A-Za-z0-9_\-/+=]{12,}",
    "jwt": r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b",
    "sql_injection": r"(?i)(?:execute|query)\s*\(\s*[f\"'].*(?:select|insert|update|delete)",
}


def scan_text(text: str) -> list[dict[str, object]]:
    findings = []
    for name, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text):
            findings.append(
                {
                    "rule": name,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "excerpt": match.group(0)[:120],
                    "severity": "high",
                }
            )
    return findings


def scan_files(root, paths=None) -> list[dict[str, object]]:
    from pathlib import Path

    base = Path(root)
    selected = [base / p for p in paths] if paths else [p for p in base.rglob("*") if p.is_file()]
    out = []
    for path in selected:
        try:
            if any(
                part in {".git", ".venv", "node_modules", ".projectmind"} for part in path.parts
            ):
                continue
            out.extend(
                {"file": str(path.relative_to(base)), **f}
                for f in scan_text(path.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError:
            continue
    return out
