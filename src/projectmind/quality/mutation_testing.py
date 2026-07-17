"""Graph-scoped mutation test command planning and confirmed execution."""

from __future__ import annotations

from pathlib import Path

from projectmind.errors import CapabilityUnavailableError
from projectmind.execution.safe_subprocess import RestrictedCommandRunner
from projectmind.models.execution_models import CommandResult


class MutationTestingService:
    def __init__(self, project_root: Path, runner: RestrictedCommandRunner) -> None:
        self.project_root = project_root.resolve()
        self.runner = runner

    def command_for(self, scope: str) -> list[str]:
        suffix = Path(scope).suffix.casefold()
        if suffix == ".py" or (self.project_root / "pyproject.toml").exists():
            return ["mutmut", "run", "--paths-to-mutate", scope]
        if (self.project_root / "package.json").exists():
            return ["npm", "test", "--", "--coverage"]
        raise CapabilityUnavailableError("no supported mutation-testing adapter detected")

    def run(self, scope: str, *, confirm: bool) -> CommandResult:
        return self.runner.run(self.command_for(scope), confirm=confirm, timeout_seconds=600)
