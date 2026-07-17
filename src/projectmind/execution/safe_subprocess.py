"""A restricted command runner; Docker is the optional true sandbox boundary."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from projectmind.config import ProjectMindSettings
from projectmind.errors import SecurityError
from projectmind.execution.path_policy import resolve_project_path
from projectmind.models.execution_models import CommandResult

SAFE_ENV_KEYS = {
    "CI",
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
    "WINDIR",
}


def _resolve_allowlisted_executable(value: str) -> str:
    """Resolve tools installed beside the active Python interpreter.

    MCP hosts commonly launch ProjectMind with ``.venv\\Scripts\\python.exe``
    without activating that environment. In that case the child process gets a
    filtered PATH that may not contain the sibling console scripts.
    """

    if Path(value).parent != Path(".") or Path(value).is_absolute():
        return value
    found = shutil.which(value)
    if found:
        return found
    interpreter_dir = Path(sys.executable).resolve().parent
    candidates = [interpreter_dir / value]
    if os.name == "nt" and not Path(value).suffix:
        candidates.extend(
            interpreter_dir / f"{value}{suffix}" for suffix in (".exe", ".cmd", ".bat")
        )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return value


class RestrictedCommandRunner:
    """Run an allowlisted argv without a shell, with bounded time and output."""

    def __init__(
        self,
        project_root: Path,
        settings: ProjectMindSettings,
    ) -> None:
        self.project_root = project_root.resolve()
        self.settings = settings

    def run(
        self,
        command: str | list[str],
        *,
        confirm: bool,
        cwd: str = ".",
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        if confirm is not True:
            raise SecurityError("explicit confirm=true is required before command execution")
        if timeout_seconds <= 0 or timeout_seconds > 3_600:
            raise SecurityError("timeout_seconds must be in (0, 3600]")
        argv = (
            shlex.split(command, posix=os.name != "nt")
            if isinstance(command, str)
            else [str(part) for part in command]
        )
        if not argv:
            raise SecurityError("command cannot be empty")
        executable = Path(argv[0]).name.casefold()
        for suffix in (".exe", ".cmd", ".bat", ".ps1"):
            if executable.endswith(suffix):
                executable = executable[: -len(suffix)]
                break
        allowed = {
            Path(item).name.casefold().removesuffix(suffix)
            for item in self.settings.security.command_allowlist
            for suffix in (".exe", ".cmd", ".bat", ".ps1", "")
        }
        if executable not in allowed:
            raise SecurityError(f"executable {argv[0]!r} is not in the command allowlist")

        resolved_cwd = resolve_project_path(self.project_root, cwd, allow_root=True)
        if not resolved_cwd.is_dir():
            raise SecurityError("command working directory does not exist or is not a directory")
        if self.settings.security.sandbox_mode == "docker":
            from projectmind.security.sandbox import DockerSandbox

            sandbox = DockerSandbox(
                docker_image=self.settings.security.docker_image,
                docker_memory=self.settings.security.docker_memory,
                docker_cpus=self.settings.security.docker_cpus,
                allowlist=self.settings.security.command_allowlist,
            )
            return sandbox.run(
                argv,
                cwd=str(resolved_cwd),
                timeout=timeout_seconds,
                mount=str(resolved_cwd),
            )

        argv[0] = _resolve_allowlisted_executable(argv[0])
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in SAFE_ENV_KEYS
        }
        started = time.perf_counter()
        process = subprocess.Popen(
            argv,
            cwd=resolved_cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            shell=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            start_new_session=os.name != "nt",
        )
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout_bytes, stderr_bytes = process.communicate()

        duration_ms = round((time.perf_counter() - started) * 1_000)
        limit = self.settings.security.max_command_output_bytes
        truncated = len(stdout_bytes) > limit or len(stderr_bytes) > limit
        stdout = stdout_bytes[:limit].decode("utf-8", errors="replace")
        stderr = stderr_bytes[:limit].decode("utf-8", errors="replace")
        return CommandResult(
            argv=argv,
            cwd=resolved_cwd.relative_to(self.project_root).as_posix() or ".",
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            truncated=truncated,
            duration_ms=duration_ms,
        )
