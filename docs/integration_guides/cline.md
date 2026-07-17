# Cline integration

ProjectMind uses stdio for the local-first path. Prefer Cline's MCP UI or `cline mcp add` because
Cline documentation currently names more than one internal settings path.

```bash
cline mcp add projectmind -- uvx --from projectmind-mcp projectmind serve --transport stdio
```

Equivalent server entry:

```json
{
  "mcpServers": {
    "projectmind": {
      "command": "uvx",
      "args": ["--from", "projectmind-mcp", "projectmind", "serve", "--transport", "stdio"],
      "env": {},
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

For a separately running local HTTP server, Cline's exact transport spelling is:

```json
{
  "mcpServers": {
    "projectmind": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8787/mcp",
      "headers": {"Authorization": "Bearer <PROJECTMIND_TOKEN>"}
    }
  }
}
```

Do not omit `type`: Cline may treat a bare URL as legacy SSE. See the
[official Cline MCP overview](https://docs.cline.bot/mcp/mcp-overview).

## Suggested project instructions

1. Call `get_relevant_context` before implementation; do not assume project structure.
2. Use `sequential_think` or `hierarchical_planning` for multi-step work and validate the plan.
3. Explore alternatives and record material architectural decisions.
4. Use `propose_edit`, review its diff, then call `confirm_and_apply` only after explicit approval.
5. Use `root_cause_analysis` and `detect_related_bugs` before speculative bug fixes.
6. Finish substantial work with `record_learning`.
7. Run commands only through `run_command_sandboxed` with confirmation.

