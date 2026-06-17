# Enterprise Rollout Defaults

The extension starts with local-only defaults:

- `aiir.strictLocalOnly = true` — Hub and network-backed commands are disabled
- `aiir.enforceWorkspaceIsolation = false` — multi-root workspaces work out of the box

For enterprise rollouts requiring workspace isolation, enable `aiir.enforceWorkspaceIsolation` and configure `aiir.allowedWorkspaceFolders`. Use `AIIR: Advanced Settings` to review all security settings.
