# AIIR Extension — Admin Deployment Guide

This guide covers installing and configuring the AIIR VS Code extension
for teams that manage deployment centrally.

## Install from VSIX

Download the extension artifact for your release:

```bash
code --install-extension aiir-<version>.vsix
```

Replace `<version>` with the target extension release (e.g., `0.5.1`).

## Recommended Settings

For regulated teams, apply the locked-down preset via workspace settings:

```json
{
  "aiir.strictLocalOnly": true,
  "aiir.enforceWorkspaceIsolation": true,
  "aiir.regulatedMode": true,
  "aiir.lockPreset": "regulated-local"
}
```

## Verify Installation

After install, open the command palette and run `AIIR: Health Check` to
confirm the CLI, git, and local scaffolding are operational.

## Managed Auto-Receipting

Enable the managed `post-commit` hook so new commits are receipted
automatically with detected AI tool attestation:

```text
AIIR: Enable Auto-Receipting
```

## Copilot Chat Integration

The extension registers an `@aiir` chat participant in Copilot Chat.
Users can generate, verify, explain, and check policy for receipts
directly from the chat interface:

- `@aiir /receipt` — Generate a receipt for the current commit
- `@aiir /verify` — Verify receipt integrity
- `@aiir /stats` — Show receipt statistics
- `@aiir /explain` — Explain what a receipt proves
- `@aiir /policy` — Check policy compliance
