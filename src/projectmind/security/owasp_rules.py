"""Small offline OWASP-oriented scanner with a Semgrep-compatible adapter boundary."""

from __future__ import annotations

import re
from pathlib import Path

from projectmind.execution.path_policy import resolve_project_path
from projectmind.models.execution_models import SecurityFinding

RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("PM001", "high", re.compile(r"\b(?:eval|exec)\s*\("), "dynamic code execution"),
    (
        "PM002",
        "high",
        re.compile(r"(?i)(?:SELECT|INSERT|UPDATE|DELETE).{0,80}(?:\+|\.format\(|f['\"]|\$\{)"),
        "SQL query appears to interpolate untrusted data",
    ),
    (
        "PM003",
        "high",
        re.compile(r"\b(?:pickle\.loads|yaml\.load)\s*\("),
        "potentially unsafe deserialisation",
    ),
    (
        "PM004",
        "medium",
        re.compile(r"(?i)innerHTML\s*=|dangerouslySetInnerHTML"),
        "HTML sink requires explicit sanitisation",
    ),
    (
        "PM005",
        "medium",
        re.compile(r"(?:open|Path)\s*\([^\n]*(?:request|params|query|argv)"),
        "user-controlled path may permit traversal",
    ),
    (
        "PM006",
        "high",
        re.compile(r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True"),
        "shell execution expands command injection risk",
    ),
)


class OwaspScanner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def scan_text(self, text: str, path: str = "<memory>") -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule_id, severity, pattern, description in RULES:
                if pattern.search(line):
                    findings.append(
                        SecurityFinding(
                            rule_id=rule_id,
                            severity=severity,
                            path=path,
                            line=line_number,
                            description=description,
                        )
                    )
        return findings

    def scan_scope(self, scope: str = ".") -> list[SecurityFinding]:
        resolved = resolve_project_path(self.project_root, scope, allow_root=True)
        candidates = [resolved] if resolved.is_file() else sorted(resolved.rglob("*"))
        findings: list[SecurityFinding] = []
        for path in candidates:
            if not path.is_file() or path.is_symlink() or ".projectmind" in path.parts:
                continue
            if path.suffix.casefold() not in {
                ".py",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".go",
                ".rs",
                ".java",
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            findings.extend(self.scan_text(text, path.relative_to(self.project_root).as_posix()))
        return findings

