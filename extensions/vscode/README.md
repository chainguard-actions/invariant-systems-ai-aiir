# AIIR for VS Code

AIIR brings AI integrity receipts into VS Code with one clear loop: record the current commit, inspect what was captured, and share proof from the same editor workflow.

The extension carries active editor context into receipts. It records only AI tools that are active at receipt time, adds `--agent-context ide:active`, and can attach deterministic editor provenance when you ask for it. The default posture stays local-only, with passive tracking off and network-backed flows gated behind explicit opt-in.

## Why it stands out

- Record proof for the current commit without leaving VS Code.
- Capture active AI tool context instead of treating installed tools as used.
- Add deterministic editor provenance when stronger source evidence is needed.
- Verify existing receipts inline with diagnostics, CodeLens, and a receipt explorer.
- Keep setup and recovery in the same flow when the CLI or local `.aiir/` scaffolding is missing.

## Core loop

1. Open a git repository in VS Code.
2. Run `AIIR: Record Commit Activity`.
3. Review the receipt, copy a shareable summary, or verify the result.

If the local `aiir` CLI or repository scaffolding is missing, `AIIR: Commit Status` routes you through setup and can resume the action you started.

## Trust defaults

- Local-only by default. Hub and other network-backed features stay disabled until you explicitly allow them.
- Passive AI edit tracking is off by default.
- Raw prompt retention is off by default. If you enable it, treat stored prompts as sensitive local data.
- Workspace isolation and allowlists are available for multi-root setups.
- Untrusted workspaces run in limited mode: viewing and verification stay available, but CLI execution and file-writing actions are disabled.
- Virtual workspaces are not supported because AIIR depends on local git and filesystem access.

## What you can do

- Generate a receipt for the current commit from the editor or SCM title bar.
- Inspect receipts in the `Status`, `Coverage`, and `Receipts` views.
- Copy a PR-ready Markdown summary with `AIIR: Copy Receipt Summary`.
- Verify receipt integrity inside VS Code.
- Generate receipts with deterministic editor provenance through `AIIR: Generate With Provenance`.
- Detect active AI tools such as Copilot, Cline, Codeium, Cursor, Continue, Tabnine, and others, then pass only active tools to the CLI.
- Initialize `.aiir` scaffolding and enable managed auto-receipting when the repository is ready.

## Optional Copilot Chat companion

`@aiir` chat and AIIR language model tools are available when GitHub Copilot Chat is present.

AIIR declares `github.copilot-chat` as a companion extension pack for those features, but the core record, inspect, and share loop does not depend on Copilot Chat.

With Copilot Chat available, you get:

- the `@aiir` chat participant for receipt, verify, stats, explain, and policy flows
- AIIR language model tools for agentic Copilot usage
- automatic routing for AI-integrity questions when Copilot decides AIIR is the right participant

## Requirements

- VS Code 1.95 or newer.
- The public `aiir` CLI installed locally for receipt generation, repository initialization, and managed auto-receipting.
- A local git repository.
- GitHub Copilot Chat only if you want `@aiir` chat or language model tool integration.

Install the CLI with:

```bash
python3 -m pip install --user aiir
```

If you prefer isolated CLI installs, `pipx install aiir` also works.

## Getting started

1. Open a git repository in VS Code.
2. Run `AIIR: Getting Started` or `AIIR: Commit Status`.
3. Use `AIIR: Record Commit Activity` for the current commit.
4. If setup is missing, let AIIR guide CLI install or `.aiir` initialization and continue the action afterward.
5. Open the receipt, preview the summary, or copy the shareable Markdown output.

## Advanced and rollout surfaces

AIIR also includes health, policy, rollout, and optional Hub surfaces, but they are intentionally not the day-one story. They stay behind deeper links, advanced commands, or explicit network opt-in so the default product stays centered on local source capture and receipt verification.

Operator docs live in the public repository:

- Threat model: <https://github.com/invariant-systems-ai/aiir/blob/main/extensions/vscode/docs/operations/THREAT_MODEL.md>
- Smoke test checklist: <https://github.com/invariant-systems-ai/aiir/blob/main/extensions/vscode/docs/operations/SMOKE_TEST.md>
- Admin rollout guide: <https://github.com/invariant-systems-ai/aiir/blob/main/extensions/vscode/docs/operations/ADMIN_DEPLOYMENT.md>

## Support

- Use `AIIR: Report a Bug` to open a prefilled public issue with extension environment details.
- Or report directly at <https://github.com/invariant-systems-ai/aiir/issues>.

## Notes

- Receipt generation, initialization, and auto-receipting use the external AIIR CLI.
- Receipt verification runs inside the extension and does not shell out to the CLI.
- The packaged extension excludes development-only files through `.vscodeignore` so release artifacts stay small.
