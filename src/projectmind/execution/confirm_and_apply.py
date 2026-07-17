"""Explicit, stale-safe application of previously reviewed proposals."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from projectmind.database import Database
from projectmind.errors import ConflictError, NotFoundError, SecurityError
from projectmind.execution.path_policy import resolve_project_path
from projectmind.execution.propose_edit import content_hash
from projectmind.models.common import utc_now
from projectmind.models.execution_models import ApplyPatchResult


class PatchApplier:
    """The sole source-file writer in ProjectMind."""

    def __init__(self, database: Database, project_root: Path) -> None:
        self.database = database
        self.project_root = project_root.resolve()

    def apply(
        self,
        patch_id: str,
        proposal_digest: str,
        *,
        confirm: bool,
    ) -> ApplyPatchResult:
        if confirm is not True:
            raise SecurityError("explicit confirm=true is required")

        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM patches WHERE id = ?", (patch_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"patch {patch_id!r} does not exist")
            if row["status"] != "proposed":
                raise ConflictError(f"patch is {row['status']}, not proposed")
            if row["proposal_digest"] != proposal_digest:
                raise SecurityError("proposal digest does not match the reviewed patch")

            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if utc_now() > expires_at:
                connection.execute(
                    "UPDATE patches SET status = 'expired' WHERE id = ?", (patch_id,)
                )
                raise ConflictError("patch proposal has expired")

            target = resolve_project_path(self.project_root, str(row["target"]))
            current = target.read_bytes() if target.exists() else b""
            actual_base_hash = content_hash(current) if target.exists() else None
            if actual_base_hash != row["base_hash"]:
                raise ConflictError("target changed after proposal; create and review a new patch")

            replacement = row["replacement_text"]
            if replacement is None:
                raise ConflictError("proposal does not contain an applicable replacement")
            encoded = str(replacement).encode("utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(target, encoded)
            resulting_hash = content_hash(encoded)
            applied_at = utc_now().isoformat()
            connection.execute(
                "UPDATE patches SET status = 'applied', applied_at = ? WHERE id = ?",
                (applied_at, patch_id),
            )

        return ApplyPatchResult(
            patch_id=patch_id,
            target=str(row["target"]),
            applied=True,
            resulting_hash=resulting_hash,
            status="applied",
        )

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".projectmind-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

