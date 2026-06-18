# AIIR CLI reference

The full catalog of `aiir` commands, grouped by task. Every command and inline
comment below is reproduced verbatim from the README so you can copy-paste with
confidence. For the discoverable-verb form and the deferred subcommand
restructure, see [cli-subcommands.md](cli-subcommands.md).

## Verification pipeline

```bash
# Verify a receipt with explanation
aiir --verify receipt.json --explain

# Verify an inference receipt (auto-detected by field signature)
aiir --verify inference_receipt.json

# Evaluate all receipts against policy, emit a Verification Summary Attestation
aiir --verify-release --policy strict --emit-vsa
```

## Common commands

```bash
# Receipt the last commit (auto-saves to .aiir/receipts.jsonl)
aiir --pretty

# Receipt a whole PR branch
aiir --range origin/main..HEAD --pretty

# Only AI-authored commits (CI mode)
aiir --ai-only --output .receipts/

# Verify with explanation
aiir --verify receipt.json --explain

# Sign + in-toto envelope (full supply-chain attestation)
aiir --sign --in-toto --output .receipts/

# Policy gate in CI
aiir --check --policy strict

# Release verification → VSA
aiir --verify-release --receipts .receipts/ --emit-vsa --policy strict
```

## Output modes

```bash
# Print JSON to stdout for piping (bypasses ledger)
aiir --json | jq .receipt_id

# JSON Lines output for streaming
aiir --range HEAD~5..HEAD --jsonl | jq .receipt_id

# Custom ledger location
aiir --ledger .audit/

# Wrap receipts in an in-toto Statement v1 envelope
aiir --range HEAD~3..HEAD --in-toto --output .receipts/

# Attach agent attestation metadata
aiir --agent-tool copilot --agent-model gpt-4o --agent-context ide
```

## Initialize

```bash
# Initialize .aiir/ directory
aiir --init                        # scaffolds receipts.jsonl, index, config, .gitignore
aiir --init --policy strict        # also creates policy.json
```

## Review — human attestation

```bash
# Review receipts — human attestation
aiir --review HEAD
aiir --review abc123 --review-outcome rejected --review-comment "needs refactor"
```

## Commit trailers

```bash
# Commit trailers
aiir --trailer                     # prints AIIR-Receipt, AIIR-Type, AIIR-AI, AIIR-Verified
```

## Policy engine

```bash
# Policy engine
aiir --policy-init strict          # creates .aiir/policy.json
aiir --check --policy strict       # CI gate: fail if policy violated
aiir --check --max-ai-percent 50   # fail if >50% commits are AI-authored
```

## Ledger utilities

```bash
# Ledger utilities
aiir --stats                       # dashboard of ledger statistics
aiir --badge                       # shields.io badge Markdown
aiir --export backup.json          # portable JSON bundle
```

## Privacy

```bash
# Privacy — omit file paths from receipts
aiir --redact-files --namespace acme-corp

# Privacy — replace email addresses with per-ledger HMAC pseudonyms
# (pseudonymous-per-ledger; see PRIVACY.md for GDPR / erasure considerations)
aiir --redact-emails
```

## GitLab CI

```bash
# Native GitLab CI mode
aiir --gitlab-ci --output .receipts/
aiir --gitlab-ci --gl-sast-report
```

## Agent receipts

```bash
# Agent receipts (aiir/agent_receipt.v0.1) — receipt a single agent action
aiir agent emit --action edit --tool claude-code --kind agent \
  --input file:src/app.py --output file:src/app.py --json
aiir agent verify receipt.json     # exit 0 = valid, 1 = tampered
```

---

See the [README](../../README.md) for the narrative overview, and
[cli-subcommands.md](cli-subcommands.md) for the discoverable-verb form and the
roadmap for the full subcommand restructure.
