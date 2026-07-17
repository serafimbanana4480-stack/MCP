"""Allowlisted linter bridge with conservative normalisation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from projectmind.execution.safe_subprocess import RestrictedCommandRunner
from projectmind.models.debug_models import NormalizedDiagnostic
from projectmind.models.execution_models import CommandResult

TEXT_DIAGNOSTIC_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+):(?P<column>\d+):\s*(?P<message>.*?)(?:\s+\[(?P<code>[^]]+)\])?$"
)


class LintersBridge:
    def __init__(self, project_root: Path, runner: RestrictedCommandRunner) -> None:
        self.project_root = project_root.resolve()
        self.runner = runner

    def run(
        self,
        scope: str = ".",
        *,
        tool: str | None = None,
        confirm: bool,
    ) -> tuple[CommandResult, list[NormalizedDiagnostic]]:
        selected = tool or self._select_tool(scope)
        commands = {
            "ruff": ["ruff", "check", scope, "--output-format", "concise"],
            "eslint": ["eslint", scope, "--format", "json"],
            "semgrep": ["semgrep", "scan", "--config", "auto", scope, "--json"],
        }
        if selected not in commands:
            raise ValueError(f"unsupported linter: {selected}")
        result = self.runner.run(commands[selected], confirm=confirm)
        return result, self._normalise(selected, result.stdout)

    def _select_tool(self, scope: str) -> str:
        suffix = Path(scope).suffix.casefold()
        if suffix == ".py" or (self.project_root / "pyproject.toml").exists():
            return "ruff"
        return "eslint"

    @staticmethod
    def _normalise(tool: str, output: str) -> list[NormalizedDiagnostic]:
        diagnostics: list[NormalizedDiagnostic] = []
        if tool in {"eslint", "semgrep"}:
            try:
                payload = json.loads(output or "[]")
            except json.JSONDecodeError:
                payload = []
            if tool == "eslint" and isinstance(payload, list):
                for file_result in payload:
                    for message in file_result.get("messages", []):
                        diagnostics.append(
                            NormalizedDiagnostic(
                                tool=tool,
                                path=file_result.get("filePath"),
                                line=message.get("line"),
                                column=message.get("column"),
                                severity="error" if message.get("severity") == 2 else "warning",
                                code=message.get("ruleId"),
                                message=message.get("message", ""),
                            )
                        )
            return diagnostics
        for line in output.splitlines():
            match = TEXT_DIAGNOSTIC_RE.match(line)
            if match:
                diagnostics.append(
                    NormalizedDiagnostic(
                        tool=tool,
                        path=match.group("path"),
                        line=int(match.group("line")),
                        column=int(match.group("column")),
                        severity="error",
                        code=match.group("code"),
                        message=match.group("message"),
                    )
                )
        return diagnostics

