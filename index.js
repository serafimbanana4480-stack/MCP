#!/usr/bin/env node
"use strict";

// npx launcher for the ProjectMind MCP server.
// Resolves a Python interpreter, installs the package via pipx/uvx when
// available, and execs the stdio server. Falls back to `python -m`.

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function findExecutable(name) {
  const candidates =
    process.platform === "win32"
      ? [name + ".exe", name + ".cmd", name + ".bat"]
      : [name];
  for (const candidate of candidates) {
    const result = spawnSync("where", [candidate], { windowsHide: true });
    if (result.status === 0 && result.stdout) {
      return result.stdout.toString().split(/\r?\n/)[0].trim();
    }
  }
  return null;
}

function run(cmd, args, opts) {
  const result = spawnSync(cmd, args, { stdio: "inherit", ...opts });
  if (result.error) {
    console.error(`Failed to launch ${cmd}: ${result.error.message}`);
    process.exit(1);
  }
  process.exit(result.status === null ? 0 : result.status);
}

function main() {
  const args = process.argv.slice(2);

  // Prefer uvx/pipx-managed execution for an isolated environment.
  const uvx = findExecutable("uvx");
  if (uvx) {
    run(uvx, ["projectmind-mcp", ...args], {});
    return;
  }
  const pipx = findExecutable("pipx");
  if (pipx) {
    run(pipx, ["run", "projectmind-mcp", ...args], {});
    return;
  }

  // Fall back to a local Python interpreter with the package importable.
  // Route through the CLI app so `serve --transport` is honoured (the
  // `projectmind.server` module ignores command-line arguments).
  const python = findExecutable("python3") || findExecutable("python");
  if (!python) {
    console.error(
      "No Python interpreter, uvx, or pipx found. Install Python 3.11+ or uv."
    );
    process.exit(1);
  }
  run(python, ["-m", "projectmind.cli.main", ...args], {});
}

main();
