"""Durable, reviewable patch proposals with no source-file mutation."""

from __future__ import annotations

import difflib
import hashlib
import re
from datetime import timedelta
from pathlib import Path

from projectmind.config import ProjectMindSettings
from projectmind.database import Database
from projectmind.errors import SecurityError
from projectmind.execution.path_policy import relative_to_root, resolve_project_path
from projectmind.models.common import new_id, utc_now
from projectmind.models.execution_models import PatchProposal
from projectmind.security.secrets_scanner import SecretScanner

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes() if path.exists() else b""


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def apply_unified_diff(original: str, patch: str) -> str:
    """Apply one standard unified diff, validating every context/deletion line."""

    source = original.splitlines(keepends=True)
    lines = patch.splitlines(keepends=True)
    output: list[str] = []
    source_index = 0
    line_index = 0
    saw_hunk = False

    while line_index < len(lines):
        line = lines[line_index]
        if line.startswith(("--- ", "+++ ", "diff ", "index ")):
            line_index += 1
            continue
        match = HUNK_RE.match(line.rstrip("\r\n"))
        if not match:
            if line.strip():
                raise SecurityError(f"unsupported unified diff line: {line[:80].rstrip()}")
            line_index += 1
            continue

        saw_hunk = True
        old_start = int(match.group(1))
        target_index = max(old_start - 1, 0)
        if target_index < source_index or target_index > len(source):
            raise SecurityError("invalid or overlapping unified diff hunk")
        output.extend(source[source_index:target_index])
        source_index = target_index
        line_index += 1

        while line_index < len(lines) and not lines[line_index].startswith("@@ "):
            hunk_line = lines[line_index]
            if hunk_line.startswith(("--- ", "+++ ")):
                break
            if hunk_line.startswith("\\ No newline at end of file"):
                line_index += 1
                continue
            if not hunk_line:
                raise SecurityError("malformed empty hunk line")
            marker, payload = hunk_line[0], hunk_line[1:]
            if marker == " ":
                if source_index >= len(source) or source[source_index] != payload:
                    raise SecurityError("unified diff context does not match current file")
                output.append(source[source_index])
                source_index += 1
            elif marker == "-":
                if source_index >= len(source) or source[source_index] != payload:
                    raise SecurityError("unified diff deletion does not match current file")
                source_index += 1
            elif marker == "+":
                output.append(payload)
            else:
                raise SecurityError(f"unsupported unified diff marker: {marker!r}")
            line_index += 1

    if not saw_hunk:
        raise SecurityError("patch does not contain a unified diff hunk")
    output.extend(source[source_index:])
    return "".join(output)


class PatchService:
    """Create immutable proposals; applying them is a separate capability."""

    def __init__(
        self,
        database: Database,
        project_root: Path,
        settings: ProjectMindSettings,
    ) -> None:
        self.database = database
        self.project_root = project_root.resolve()
        self.settings = settings
        self.secret_scanner = SecretScanner(self.project_root)

    def propose(
        self,
        target: str,
        patch: str,
        *,
        patch_format: str = "auto",
    ) -> PatchProposal:
        resolved = resolve_project_path(self.project_root, target)
        relative = relative_to_root(self.project_root, resolved)
        original_bytes = _read_bytes(resolved)
        try:
            original = original_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SecurityError("binary or non-UTF-8 targets are not supported") from exc

        looks_unified = any(line.startswith("@@ ") for line in patch.splitlines())
        if patch_format == "unified" or (patch_format == "auto" and looks_unified):
            replacement = apply_unified_diff(original, patch)
            unified_diff = patch
        elif patch_format in {"auto", "replacement"}:
            replacement = patch
            newline = _detect_newline(original)
            unified_diff = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    replacement.splitlines(keepends=True),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                    lineterm=newline,
                )
            )
        else:
            raise SecurityError("patch_format must be auto, replacement, or unified")

        if replacement == original:
            raise SecurityError("proposal does not change the target")

        created_at = utc_now()
        expires_at = created_at + timedelta(seconds=self.settings.security.patch_ttl_seconds)
        patch_id = new_id("patch")
        base_hash = content_hash(original_bytes) if resolved.exists() else None
        digest_payload = "\x1f".join(
            [patch_id, relative, base_hash or "<missing>", replacement, expires_at.isoformat()]
        )
        proposal_digest = hashlib.sha256(digest_payload.encode("utf-8")).hexdigest()

        findings = self.secret_scanner.scan_text(replacement, relative)
        warnings = [f"{item.rule_id} at line {item.line}: {item.description}" for item in findings]
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO patches(
                    id, target, unified_diff, replacement_text, base_hash,
                    proposal_digest, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?)
                """,
                (
                    patch_id,
                    relative,
                    unified_diff,
                    replacement,
                    base_hash,
                    proposal_digest,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )

        return PatchProposal(
            patch_id=patch_id,
            target=relative,
            unified_diff=unified_diff,
            proposal_digest=proposal_digest,
            base_hash=base_hash,
            created_at=created_at,
            expires_at=expires_at,
            warnings=warnings,
        )

