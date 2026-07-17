"""Reviewable minimal-reproduction proposals; this module never writes tests."""

from __future__ import annotations

import re
from pathlib import Path

from projectmind.models.debug_models import ReproductionProposal, RootCauseReport


def _safe_test_stem(value: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return (stem or "reported_issue")[:60]


class ReproductionGenerator:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def propose(self, description: str, analysis: RootCauseReport) -> ReproductionProposal:
        target_paths = [candidate.path for candidate in analysis.candidates[:3]]
        python_target = next((path for path in target_paths if path.endswith(".py")), None)
        stem = _safe_test_stem(description.splitlines()[0] if description else "reported issue")
        if python_target:
            test_path = f"tests/test_regression_{stem}.py"
            test_content = (
                '"""Regression reproduction generated as a review-only proposal."""\n\n'
                "import pytest\n\n\n"
                f"def test_{stem}() -> None:\n"
                "    # Arrange: replace this placeholder with the smallest failing input.\n"
                "    # Act: call the indexed target identified by root-cause analysis.\n"
                "    # Assert: encode the expected behaviour before applying a fix.\n"
                '    pytest.fail("complete the reviewed reproduction before applying")\n'
            )
            command = ["pytest", test_path, "-q"]
        else:
            test_path = f"tests/regression_{stem}.md"
            test_content = (
                f"# Regression reproduction: {description.splitlines()[0][:120]}\n\n"
                "1. Record the smallest input that still fails.\n"
                "2. Invoke the narrowest target listed below.\n"
                "3. Capture the expected and actual output.\n"
                "4. Convert this scenario to the project's native test framework.\n"
            )
            command = []
        return ReproductionProposal(
            test_path=test_path,
            test_content=test_content,
            target_paths=target_paths,
            assumptions=[
                "The proposal is a scaffold and must be reviewed.",
                "No command is run and no file is written by reproduction generation.",
            ],
            command=command,
        )

