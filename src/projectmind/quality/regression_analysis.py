"""Select related tests from graph evidence before confirmed execution."""

from __future__ import annotations

import re
from pathlib import Path

from projectmind.database import Database
from projectmind.execution.safe_subprocess import RestrictedCommandRunner
from projectmind.models.debug_models import RegressionPlan
from projectmind.models.execution_models import CommandResult

DIFF_PATH_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


class RegressionAnalyzer:
    def __init__(
        self,
        database: Database,
        project_root: Path,
        runner: RestrictedCommandRunner,
    ) -> None:
        self.database = database
        self.project_root = project_root.resolve()
        self.runner = runner

    def plan(self, fix_diff: str) -> RegressionPlan:
        changed = sorted(set(DIFF_PATH_RE.findall(fix_diff)))
        tests: set[str] = set()
        with self.database.connect() as connection:
            for path in changed:
                rows = connection.execute(
                    """
                    SELECT DISTINCT test_nodes.path
                    FROM nodes changed_nodes
                    JOIN edges e ON e.target_id = changed_nodes.id AND e.type = 'tests'
                    JOIN nodes test_nodes ON test_nodes.id = e.source_id
                    WHERE changed_nodes.path = ?
                    """,
                    (path,),
                ).fetchall()
                tests.update(str(row["path"]) for row in rows)
        commands: list[list[str]] = []
        python_tests = sorted(path for path in tests if path.endswith(".py"))
        js_tests = sorted(
            path for path in tests if Path(path).suffix.casefold() in {".js", ".ts", ".tsx"}
        )
        if python_tests:
            commands.append(["pytest", *python_tests, "-q"])
        if js_tests:
            commands.append(["npm", "test", "--", *js_tests])
        if not commands and any(path.endswith(".py") for path in changed):
            commands.append(["pytest", "-q"])
        return RegressionPlan(
            changed_targets=changed,
            related_tests=sorted(tests),
            commands=commands,
            rationale=[
                "Tests are selected from indexed TESTS edges.",
                "A language-level fallback is used only when no relation is indexed.",
            ],
        )

    def run(self, plan: RegressionPlan, *, confirm: bool) -> list[CommandResult]:
        return [
            self.runner.run(command, confirm=confirm, timeout_seconds=600)
            for command in plan.commands
        ]

