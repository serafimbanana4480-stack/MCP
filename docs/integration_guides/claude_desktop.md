# Claude Desktop integration

For local-first ProjectMind, use stdio. Open Settings → Developer → Edit Config and add:

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

Configuration locations:

- Windows: `%APPDATA%\\Claude\\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Fully quit and restart Claude Desktop after editing. The official local-server guide is at
[modelcontextprotocol.io](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

Remote custom connectors are reached from Anthropic infrastructure, so localhost is not
reachable there and OAuth/public HTTPS is expected. That path conflicts with ProjectMind's
default local-first use; do not publish the local endpoint merely to configure Desktop.

## Suggested project instructions

1. Call `get_relevant_context` before implementation; do not assume project structure.
2. Use `sequential_think` or `hierarchical_planning` for multi-step work and validate the plan.
3. Explore alternatives and record material architectural decisions.
4. Use `propose_edit`, review its diff, then call `confirm_and_apply` only after explicit approval.
5. Use `root_cause_analysis` and `detect_related_bugs` before speculative bug fixes.
6. Finish substantial work with `record_learning`.
7. Run commands only through `run_command_sandboxed` with confirmation.

