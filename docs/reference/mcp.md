# MCP server

AIIR ships an MCP server (`aiir-mcp-server`) so an AI assistant can generate and
verify receipts as tools, over stdio. Point your assistant at it and it can
receipt its own work after writing code.

Seven tools: `aiir_receipt`, `aiir_verify`, `aiir_stats`, `aiir_explain`, `aiir_policy_check`, `aiir_verify_release`, `aiir_gitlab_summary`.

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "aiir": { "command": "aiir-mcp-server", "args": ["--stdio"] }
  }
}
```

**VS Code / Copilot** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "aiir": { "command": "aiir-mcp-server", "args": ["--stdio"] }
  }
}
```

Also works with Cursor (`.cursor/mcp.json`), Continue (`.continue/mcpServers/`), Cline (`cline_mcp_settings.json`), and Windsurf (`~/.codeium/windsurf/mcp_config.json`).

See the [documentation index](../README.md) and the [CLI reference](cli.md).
