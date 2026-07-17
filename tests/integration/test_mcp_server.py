from __future__ import annotations

from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from projectmind.server import create_server


@pytest.mark.anyio
async def test_real_sdk_client_lists_and_calls_ping(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    async with create_connected_server_and_client_session(
        server,
        raise_exceptions=True,
    ) as session:
        listing = await session.list_tools()
        tools = {tool.name: tool for tool in listing.tools}
        assert "ping" in tools
        assert "propose_edit" in tools
        assert tools["ping"].inputSchema["type"] == "object"
        assert tools["ping"].outputSchema is not None

        response = await session.call_tool("ping", {})
        assert response.isError is False
        assert response.structuredContent is not None
        assert response.structuredContent["status"] == "ok"
        assert response.structuredContent["database_ready"] is True


@pytest.mark.anyio
async def test_mcp_patch_flow_cannot_apply_without_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "example.py"
    target.write_text("before = True\n", encoding="utf-8")
    server = create_server(tmp_path)
    async with create_connected_server_and_client_session(
        server,
        raise_exceptions=False,
    ) as session:
        proposal = await session.call_tool(
            "propose_edit",
            {
                "target": "example.py",
                "patch": "before = False\n",
                "patch_format": "replacement",
            },
        )
        assert proposal.isError is False
        assert proposal.structuredContent is not None
        assert target.read_text(encoding="utf-8") == "before = True\n"

        denied = await session.call_tool(
            "confirm_and_apply",
            {
                "patch_id": proposal.structuredContent["patch_id"],
                "proposal_digest": proposal.structuredContent["proposal_digest"],
                "confirm": False,
            },
        )
        assert denied.isError is True
        assert target.read_text(encoding="utf-8") == "before = True\n"


@pytest.mark.anyio
async def test_mcp_consolidation_parameter_and_tool_telemetry(tmp_path: Path) -> None:
    server = create_server(tmp_path)
    async with create_connected_server_and_client_session(
        server, raise_exceptions=True
    ) as session:
        await session.call_tool(
            "record_decision", {"content": "Keep SQLite for project memory", "tags": ["db"]}
        )
        await session.call_tool(
            "record_decision", {"content": "Use SQLite as durable memory", "tags": ["db"]}
        )
        consolidated = await session.call_tool(
            "consolidate_memory", {"min_cluster_size": 2}
        )
        assert consolidated.isError is False
        assert consolidated.structuredContent is not None
        assert consolidated.structuredContent["consolidated"]

        await session.call_tool("get_graph_summary", {})
        stats = await session.call_tool("get_usage_stats", {})
        assert stats.structuredContent is not None
        assert stats.structuredContent["calls"] >= 4
        tool_names = {row["tool_name"] for row in stats.structuredContent["tools"]}
        assert {"record_decision", "consolidate_memory", "get_graph_summary"} <= tool_names
