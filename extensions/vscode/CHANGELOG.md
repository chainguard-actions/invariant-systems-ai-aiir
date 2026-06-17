# Changelog

All notable changes to the AIIR VS Code extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.4.1]

### Fixed

- Rewired scripted panel actions away from inline `onclick` handlers so nonce-based webview CSP no longer leaves Marketplace-installed buttons inert.
- Surfaced webview command failures in the AIIR output channel and user-visible error notifications instead of failing silently.

## [0.4.0]

### Changed

- Decoupled the VS Code extension release line from the core AIIR package releases so the Marketplace sidecar can ship on its own semver.
- Tightened the public Marketplace narrative around the local-first record, inspect, and share loop, active-tool-only capture, and deterministic editor provenance.

## [1.2.5]

### Added

- **`@aiir` Copilot Chat participant** — ask questions about receipts, verification, and policy directly in Copilot Chat with five slash commands (`/receipt`, `/verify`, `/stats`, `/explain`, `/policy`).
- **Native language model tools** — five tools (`aiir_receipt`, `aiir_verify`, `aiir_stats`, `aiir_explain`, `aiir_policy_check`) available to Copilot's agentic mode and any extension that consumes the VS Code LanguageModelTool API.
- **Chat participant detection** — Copilot can automatically route AI-integrity questions to `@aiir` without explicit mention.
- Deep smoke test launcher (`scripts/launch-deep-smoke.sh`) and admin deployment guide (`docs/operations/ADMIN_DEPLOYMENT.md`).

### Changed

- Minimum VS Code version raised to **1.95** (from 1.85) for `vscode.chat` and `vscode.lm` APIs.
- Extension now declares `github.copilot-chat` as an optional companion extension pack for first-class Copilot integration.
- Extension categories now include `AI`.
- Repaired receipt UX now treats the newest receipt for a commit as the active one, so superseded failures stop driving the primary attention state.
- Passive AI edit tracking now defaults to off and is described more explicitly in public settings and README copy.
- Local receipt generation now records only active AI tools and no longer falls back to installed-but-inactive extensions.
- Extension activation no longer depends on opening arbitrary JSON files.

### Fixed

- `Verify All Receipts` now refreshes the Home view as well as the explorer.

## [0.3.0]

### Added

- Automatic AI coding tool detection: the extension now scans for active AI extensions (Copilot, Cline, Codeium, Cursor, Continue, Tabnine, Amazon Q, Cody, Supermaven, Blackbox AI, AskCodi, Bito, Pieces) and passes `--agent-tool` and `--agent-context` flags to the CLI during receipt generation and auto-receipting.
- Health check and setup check views now display detected AI coding tools.
- Control panel shows live AI tool detection status.
- Receipt Explorer with commit-centric grouped browsing by repository, status, and recency.
- Native sidebar layout with Receipt Explorer, Actions, and Posture views.
- Setup check, security posture, deployment presets, and advanced settings operator surfaces.
- Managed `post-commit` hook with automatic AI tool injection.
- Multi-root workspace support with folder allowlists and isolation enforcement.
- Strict local-only mode enabled by default.
- CodeLens inline verification for receipt files.
- Home view with human-first landing page, trust status, next best action, and current repository snapshot (branch, working tree, auto-receipting state, HEAD coverage).
- CBOR sidecar prominence: receipt detail now shows CBOR file size, SHA-256 hash, and an inline Verify CBOR action.
- Sigstore first-class promotion: signed receipts surface Sigstore bundle size, hash, interactive Verify Sigstore action, and coverage gap warnings when signing is absent.
- Expanded receipt detail fields: v2 DAG binding (`parent_receipt_ids`), content integrity hashes (`content_hash_sha256`), `detection_method` per signal, and agent attestation extensions.

### Removed

- `declared_tools` phantom field removed from receipt detail rendering.

## [0.2.0]

### Added

- Receipt discovery and inline verification.
- Getting Started walkthrough.
- Hub integration commands (optional, disabled by default).

## [0.1.0]

### Added

- Initial release with receipt viewing and basic verification.
