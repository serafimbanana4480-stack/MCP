"""Offline secret detection using redacted prefix patterns and entropy."""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from projectmind.execution.path_policy import resolve_project_path
from projectmind.models.execution_models import SecurityFinding

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key-like value"),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"), "GitHub token-like value"),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "API key-like value"),
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "private key material",
    ),
    (
        "generic-secret-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]([^'\"]{12,})['\"]"
        ),
        "hard-coded credential-like assignment",
    ),
)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in Counter(value).values())


def redact(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


class SecretScanner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def scan_text(self, text: str, path: str = "<memory>") -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            occupied: set[tuple[int, int]] = set()
            for rule_id, pattern, description in PATTERNS:
                for match in pattern.finditer(line):
                    occupied.add(match.span())
                    value = match.group(1) if match.lastindex else match.group(0)
                    findings.append(
                        SecurityFinding(
                            rule_id=rule_id,
                            severity="critical" if rule_id == "private-key" else "high",
                            path=path,
                            line=line_number,
                            description=description,
                            redacted_match=redact(value),
                        )
                    )
            for candidate in re.findall(r"[A-Za-z0-9+/=_-]{32,}", line):
                start = line.find(candidate)
                if any(left <= start < right for left, right in occupied):
                    continue
                if shannon_entropy(candidate) >= 4.2:
                    findings.append(
                        SecurityFinding(
                            rule_id="high-entropy-string",
                            severity="medium",
                            path=path,
                            line=line_number,
                            description="high-entropy string may contain a secret",
                            redacted_match=redact(candidate),
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
            if path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            relative = path.relative_to(self.project_root).as_posix()
            findings.extend(self.scan_text(text, relative))
        return findings

