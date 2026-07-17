# Cursor integration

Create `.cursor/mcp.json` in the project (or `~/.cursor/mcp.json` for a user-wide entry):

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

Cursor infers Streamable HTTP from a `url` entry:

```json
{
  "mcpServers": {
    "projectmind": {
      "url": "http://127.0.0.1:8787/mcp",
      "headers": {"Authorization": "Bearer ${env:PROJECTMIND_TOKEN}"}
    }
  }
}
```

See the [official Cursor MCP reference](https://cursor.com/docs/mcp.md).

## Suggested project instructions

1. Call `get_relevant_context` before implementation; do not assume project structure.
2. Use `sequential_think` or `hierarchical_planning` for multi-step work and validate the plan.
3. Explore alternatives and record material architectural decisions.
4. Use `propose_edit`, review its diff, then call `confirm_and_apply` only after explicit approval.
5. Use `root_cause_analysis` and `detect_related_bugs` before speculative bug fixes.
6. Finish substantial work with `record_learning`.
7. Run commands only through `run_command_sandboxed` with confirmation.

