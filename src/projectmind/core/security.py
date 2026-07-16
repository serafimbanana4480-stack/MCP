from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .config import Config
from .exceptions import SecurityViolation

DESTRUCTIVE = {
    "rm",
    "rmdir",
    "del",
    "erase",
    "format",
    "shutdown",
    "reboot",
    "mkfs",
}


def validate_command(command: str, config: Config) -> list[str]:
    parts = shlex.split(command, posix=False)
    if not parts:
        raise SecurityViolation("Comando vazio")
    executable = Path(parts[0]).name.lower()
    if executable not in {Path(x).name.lower() for x in config.allowed_commands}:
        raise SecurityViolation(f"Comando não permitido: {executable}")
    tokens = {t.lower() for t in parts}
    if (
        DESTRUCTIVE & tokens
        or any(("git", verb) in zip(tokens, tokens[1:]) for verb in ("reset", "clean"))
        or ">" in command
        or "&&" in command
        or "|" in command
    ):
        raise SecurityViolation("Comando potencialmente destrutivo ou com encadeamento recusado")
    return parts


def run_sandbox(command: str, config: Config, timeout: int | None = None) -> dict[str, object]:
    parts = validate_command(command, config)
    proc = subprocess.run(
        parts,
        cwd=config.root,
        capture_output=True,
        text=True,
        timeout=min(timeout or config.command_timeout, 300),
        shell=False,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-12000:],
    }
