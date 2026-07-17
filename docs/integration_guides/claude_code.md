# Claude Code integration

Add a project-scoped stdio server:

```powershell
claude mcp add --transport stdio --scope project projectmind -- uvx --from projectmind-mcp projectmind serve --transport stdio
```

Equivalent `.mcp.json`:

```json
{
  "mcpServers": {
    "projectmind": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "projectmind-mcp", "projectmind", "serve", "--transport", "stdio"],
      "env": {}
    }
  }
}
```

For the authenticated loopback HTTP server:

```powershell
claude mcp add --transport http --scope project projectmind http://127.0.0.1:8787/mcp --header "Authorization: Bearer <PROJECTMIND_TOKEN>"
```

Claude Code calls the transport `http` (alias `streamable-http`). Verify with `claude mcp list`,
`claude mcp get projectmind`, and `/mcp` inside a session. See the
[official Claude Code MCP reference](https://code.claude.com/docs/en/mcp).

## Suggested project instructions

1. Call `get_relevant_context` before implementation; do not assume project structure.
2. Use `sequential_think` or `hierarchical_planning` for multi-step work and validate the plan.
3. Explore alternatives and record material architectural decisions.
4. Use `propose_edit`, review its diff, then call `confirm_and_apply` only after explicit approval.
5. Use `root_cause_analysis` and `detect_related_bugs` before speculative bug fixes.
6. Finish substantial work with `record_learning`.
7. Run commands only through `run_command_sandboxed` with confirmation.

