"""Real Docker-based sandbox for command execution.

This module provides :class:`DockerSandbox`, which runs a command inside an
ephemeral Docker container with restricted resources and no network access.
It is used by :mod:`projectmind.execution.safe_subprocess` when the configured
sandbox mode is ``"docker"``.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess

from projectmind.errors import CapabilityUnavailableError
from projectmind.models.execution_models import CommandResult


class DockerSandbox:
    """Run commands inside a disposable Docker container.

    The container is created with ``--rm`` so it is removed after the command
    exits. Network access is disabled (``--network none``) and resource limits
    are applied from the supplied configuration.
    """

    def __init__(
        self,
        docker_image: str | None = None,
        docker_memory: str = "512m",
        docker_cpus: float = 1.0,
        allowlist: list[str] | None = None,
    ) -> None:
        self.docker_image = docker_image or "python:3.12-slim"
        self.docker_memory = docker_memory
        self.docker_cpus = docker_cpus
        self.allowlist = allowlist or []
        self._docker_bin = shutil.which("docker")

    def _ensure_docker(self) -> str:
        if not self._docker_bin:
            raise CapabilityUnavailableError(
                "docker CLI not found on PATH; cannot run sandboxed command"
            )
        return self._docker_bin

    def _validate_command(self, command: list[str]) -> None:
        if not command:
            raise CapabilityUnavailableError("empty command rejected by sandbox")
        executable = command[0]
        if self.allowlist and executable not in self.allowlist:
            raise CapabilityUnavailableError(
                f"command '{executable}' not in sandbox allowlist"
            )

    def run(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: float | None = None,
        mount: str | None = None,
    ) -> CommandResult:
        """Execute ``command`` inside a Docker container.

        Args:
            command: The argv list to run.
            cwd: Host directory to mount into the container at ``/work`` and use
                as the working directory.
            timeout: Optional timeout in seconds.
            mount: Optional explicit host path to mount (defaults to ``cwd``).

        Returns:
            A :class:`CommandResult` describing the outcome.
        """
        docker = self._ensure_docker()
        self._validate_command(command)

        workdir = mount or cwd or "."
        container_cmd = " ".join(shlex.quote(part) for part in command)

        argv = [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            self.docker_memory,
            "--cpus",
            str(self.docker_cpus),
            "-v",
            f"{workdir}:/work",
            "-w",
            "/work",
            self.docker_image,
            "sh",
            "-c",
            container_cmd,
        ]

        try:
            proc = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return CommandResult(
                argv=argv,
                cwd=cwd or workdir,
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                timed_out=False,
                truncated=False,
                duration_ms=0,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                argv=argv,
                cwd=cwd or workdir,
                returncode=-1,
                stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
                stderr="command timed out inside docker sandbox",
                timed_out=True,
                truncated=False,
                duration_ms=0,
            )
