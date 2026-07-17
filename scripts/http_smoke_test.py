"""Validate a real Streamable HTTP MCP process with the official SDK client."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main() -> int:
    with tempfile.TemporaryDirectory(prefix="projectmind-http-") as raw_root:
        root = Path(raw_root)
        (root / "example.py").write_text("value = 1\n", encoding="utf-8")
        port = 8791
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "projectmind.cli.main",
                "serve",
                "--transport",
                "streamable-http",
                "--root",
                str(root),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await asyncio.sleep(2)
            async with (
                streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
                    read_stream,
                    write_stream,
                    _,
                ),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                tools = await session.list_tools()
                ping = await session.call_tool("ping", {})
                print(
                    {
                        "tools": len(tools.tools),
                        "ping_ok": ping.isError is False,
                        "database_ready": ping.structuredContent["database_ready"],
                    }
                )
                return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
