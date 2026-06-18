# Claude Code Hooks → AIIR Receipt

> Auto-generate an AIIR receipt every time Claude Code writes code, with
> declared AI provenance so the receipt shows `AI: YES`.
> Uses Claude Code's [hooks system](https://code.claude.com/docs/en/hooks)
> to run `aiir` after each commit that Claude makes.

## Quick Setup

### 1. Install AIIR

```bash
pip install aiir
```

### 2. Configure your commit workflow

**Important**: Do NOT use `--no-verify` and auto-commit every file edit.
That approach creates commits with no detectable AI trailer and produces
`AI: NO` receipts, which defeats the purpose.

The correct workflow:

1. Let Claude Code make changes normally (no auto-commit hook on every edit)
2. When Claude is done with a logical unit of work, **you commit** with a
   declaration trailer that AIIR can detect:

```bash
# Commit with a declared AI trailer (AIIR detects 'Co-authored-by: Claude')
git commit -m "feat: add auth middleware

Co-authored-by: Claude <claude@anthropic.com>"
```

Then AIIR generates the receipt:

```bash
aiir --pretty
```

### 3. Add a PostToolUse hook for receipting

Add the following to `.claude/settings.json` to auto-receipt after Claude
commits (not after every file edit):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && git diff --quiet HEAD && aiir --pretty 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

This runs `aiir --pretty` after every Bash tool use that results in a new
commit (detected by `git diff --quiet HEAD` being true after the command).
It does NOT auto-commit; Claude commits with its own trailer declarations.

### Example output — with declared AI provenance

```text
┌─ Receipt: g1-a3f8b2c1d4e5f6a7b8c9d0e1
│  Commit:  c4dec85630
│  Subject: feat: add auth middleware
│  Author:  Jane Dev <jane@example.com>
│  Files:   3 changed
│  AI:      YES (co-authored-by:claude)
│  Hash:    sha256:7f3a...
│  Time:    2026-03-09T14:22:01Z
│  Signed:  none
└──────────────────────────────────────────
```

The `AI: YES` signal comes from the `Co-authored-by: Claude` trailer in the
commit message. Without a trailer, the receipt shows `AI: NO`.

## Variations

### Signed receipts with agent attestation (recommended for teams)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && git diff --quiet HEAD && aiir --agent-tool claude-code --agent-model claude-sonnet --agent-context ide --sign --output .receipts/ 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

Requires `pip install aiir[sign]` and a Sigstore OIDC token.

This adds structured metadata to `extensions.agent_attestation` and
cryptographically signs the receipt:

```json
{
  "extensions": {
    "agent_attestation": {
      "tool_id": "claude-code",
      "model_class": "claude-sonnet",
      "run_context": "ide",
      "confidence": "declared"
    }
  }
}
```

### In-toto envelope (supply-chain integration)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && git diff --quiet HEAD && aiir --in-toto --json > .receipts/latest-intoto.json 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

The output is a standard in-toto Statement v1 envelope that any
SLSA verifier, Sigstore policy-controller, or OPA/Gatekeeper policy
can consume directly.

### Quiet mode (no terminal output)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && git diff --quiet HEAD && aiir --quiet 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

## Combine with MCP

You can also use AIIR as an MCP tool alongside hooks. Add to
`.claude/mcp.json`:

```json
{
  "mcpServers": {
    "aiir": {
      "command": "aiir-mcp-server",
      "args": ["--stdio"]
    }
  }
}
```

Now Claude Code can _also_ call `aiir_receipt` and `aiir_verify`
as tools, useful for verification workflows and on-demand receipting.

## Verify receipts

```bash
# Verify a single receipt
aiir --verify .receipts/receipt_c4dec85630_7f3a1b2c.json

# Verify with human-readable explanation
aiir --verify .receipts/receipt_c4dec85630_7f3a1b2c.json --explain

# Verify all receipts in a directory
for f in .receipts/*.json; do aiir --verify "$f"; done

# Check ledger health
aiir --stats
```

## Policy enforcement

Add a policy to fail CI when too many commits are AI-authored:

```bash
# Initialize strict policy (max 50% AI, signing required)
aiir --policy-init strict

# Check policy against ledger
aiir --check --policy strict
```

---

## Agent receipts (PostToolUse)

Commit receipts only see what is _declared in the commit message_. Chat- and
agent-mode assistants frequently leave no trailer, so the commit receipt comes
back `AI: NO` even though an agent did the work. The
[agent-receipt profile](../integrations/agent-receipt-contract.md) closes that gap: a
**PostToolUse** hook emits a small, declared-agent receipt for each agent action
_before_ the commit, so the provenance exists independently of the commit text.

Add this to `.claude/settings.json`. It records that an agent edit happened,
with no file contents, only references:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && aiir agent emit --action edit --tool claude-code --kind agent --surface cli --summary 'agent edit' >/dev/null 2>&1 || true"
          }
        ]
      }
    ]
  }
}
```

Each fired hook appends an `aiir/agent_receipt.v0.1` record to
`.aiir/receipts.jsonl`. Verify them like any other receipt:

```bash
aiir agent verify <receipt.json>   # or: aiir verify <receipt.json>
```

Notes:

- The hook is best-effort (`|| true`) so it never blocks your edit flow.
- It records **references and metadata only**, never file contents or prompts.
- Pair it with a commit-receipt step (above) so a PR carries both the
  fine-grained agent trail and the commit-level receipt.
- For a policy decision, pass `--policy allowed|warned|blocked|needs_review`
  and `--policy-reason "<why>"` (repeatable).

---

**Links**: [AIIR on PyPI](https://pypi.org/project/aiir/) ·
[AIIR on GitHub](https://github.com/invariant-systems-ai/aiir) ·
[Claude Code Hooks docs](https://code.claude.com/docs/en/hooks)
