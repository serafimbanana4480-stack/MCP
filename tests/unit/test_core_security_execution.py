from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from projectmind.config import ProjectMindSettings, ScoringWeights
from projectmind.database import Database
from projectmind.errors import ConflictError, SecurityError
from projectmind.execution.confirm_and_apply import PatchApplier
from projectmind.execution.propose_edit import PatchService, apply_unified_diff
from projectmind.execution.safe_subprocess import RestrictedCommandRunner
from projectmind.security.owasp_rules import OwaspScanner
from projectmind.security.secrets_scanner import SecretScanner
from projectmind.telemetry.events import TelemetryStore
from projectmind.telemetry.self_improvement import SelfImprovementReporter


def make_database(root: Path) -> Database:
    database = Database(root / ".projectmind" / "projectmind.db", root)
    database.initialize()
    return database


def test_scoring_weights_require_a_normalized_distribution() -> None:
    with pytest.raises(ValidationError, match=r"sum to 1\.0"):
        ScoringWeights(graph_relevance=0.2)


def test_database_initialization_is_idempotent_and_enables_foreign_keys(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
        assert connection.execute("SELECT root_path FROM project_state").fetchone()[0] == str(
            tmp_path.resolve()
        )


def test_unified_diff_validates_context() -> None:
    patch = """--- a/example.txt
+++ b/example.txt
@@ -1,2 +1,2 @@
 alpha
-beta
+gamma
"""
    assert apply_unified_diff("alpha\nbeta\n", patch) == "alpha\ngamma\n"
    with pytest.raises(SecurityError, match=r"context|deletion"):
        apply_unified_diff("changed\nbeta\n", patch)


def test_patch_requires_review_digest_and_unchanged_base(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    database = make_database(tmp_path)
    settings = ProjectMindSettings()
    service = PatchService(database, tmp_path, settings)
    applier = PatchApplier(database, tmp_path)

    proposal = service.propose("module.py", "value = 2\n", patch_format="replacement")
    assert "-value = 1" in proposal.unified_diff
    assert target.read_text(encoding="utf-8") == "value = 1\n"

    with pytest.raises(SecurityError, match="confirm"):
        applier.apply(proposal.patch_id, proposal.proposal_digest, confirm=False)
    with pytest.raises(SecurityError, match="digest"):
        applier.apply(proposal.patch_id, "wrong", confirm=True)

    result = applier.apply(proposal.patch_id, proposal.proposal_digest, confirm=True)
    assert result.applied is True
    assert target.read_text(encoding="utf-8") == "value = 2\n"
    assert result.resulting_hash == hashlib.sha256(b"value = 2\n").hexdigest()
    with pytest.raises(ConflictError, match="not proposed"):
        applier.apply(proposal.patch_id, proposal.proposal_digest, confirm=True)


def test_patch_rejects_traversal_and_stale_targets(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("before\n", encoding="utf-8")
    database = make_database(tmp_path)
    service = PatchService(database, tmp_path, ProjectMindSettings())
    applier = PatchApplier(database, tmp_path)

    with pytest.raises(SecurityError, match="traversal"):
        service.propose("../escape.py", "bad")

    proposal = service.propose("module.py", "after\n")
    target.write_text("concurrent change\n", encoding="utf-8")
    with pytest.raises(ConflictError, match="changed after proposal"):
        applier.apply(proposal.patch_id, proposal.proposal_digest, confirm=True)


def test_scanners_redact_secrets_and_flag_unsafe_patterns(tmp_path: Path) -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    secret_findings = SecretScanner(tmp_path).scan_text(f'API_KEY = "{secret}"\n', "config.py")
    assert any(item.rule_id == "openai-key" for item in secret_findings)
    assert all(secret not in (item.redacted_match or "") for item in secret_findings)

    findings = OwaspScanner(tmp_path).scan_text("result = eval(user_input)\n", "app.py")
    assert findings[0].rule_id == "PM001"


def test_restricted_runner_requires_confirmation_and_allowlist(tmp_path: Path) -> None:
    settings = ProjectMindSettings()
    executable = Path(sys.executable).name
    settings.security.command_allowlist = [executable]
    runner = RestrictedCommandRunner(tmp_path, settings)

    with pytest.raises(SecurityError, match="confirm"):
        runner.run([sys.executable, "-c", "print('ok')"], confirm=False)
    result = runner.run([sys.executable, "-c", "print('ok')"], confirm=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"


def test_telemetry_is_local_anonymized_and_actionable(tmp_path: Path) -> None:
    database = make_database(tmp_path)
    settings = ProjectMindSettings()
    telemetry = TelemetryStore(database, settings)
    telemetry.record(
        "get_relevant_context",
        success=True,
        latency_ms=120,
        tokens_used=300,
        metadata={"task": "secret project name", "mode": "surgical"},
    )
    stats = telemetry.usage_stats()
    assert stats["calls"] == 1
    assert stats["success_rate"] == 1.0

    with database.connect() as connection:
        metadata = connection.execute("SELECT metadata_json FROM telemetry_events").fetchone()[0]
    assert "secret project name" not in metadata
    report = SelfImprovementReporter(telemetry).report()
    assert len(report.suggestions) >= 2
    assert report.applied_automatically is False

