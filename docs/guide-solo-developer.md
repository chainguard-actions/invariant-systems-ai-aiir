# Adoption Guide: Solo Developer

**Time to first receipt: under 5 minutes.**

You work alone or on a small team. You use Copilot, Cursor, or ChatGPT to write
code. You want a record of which commits involved AI — for yourself, for
compliance, or just to know.

---

## Step 1 — Install and receipt

```bash
pip install aiir        # zero dependencies, Python 3.9+
cd your-repo
aiir --pretty           # receipt your last commit
```

Your receipt is now in `.aiir/receipts.jsonl`. Commit it:

```bash
git add .aiir/
git commit -m "chore: add AIIR receipts"
```

## Step 2 — Verify

```bash
aiir --verify .aiir/receipts.jsonl --explain
```

If the receipt is untouched, verification passes. Change one byte and it fails —
that's the tamper-evidence.

## Step 3 — Make it automatic

### Option A: pre-commit hook (recommended)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/invariant-systems-ai/aiir
    rev: v1.4.0
    hooks:
      - id: aiir
```

Every commit gets receipted automatically at post-commit stage.

### Option B: VS Code extension

Install [AIIR for VS Code](https://marketplace.visualstudio.com/items?itemName=invariant-systems.aiir),
then use **AIIR: Record Commit Activity** from the command palette after each
commit.

### Option C: enable auto-receipting in the extension

Open the command palette → **AIIR: Enable Auto-Receipting**. The extension
will receipt new commits automatically when it detects them.

## Step 4 — Receipt a branch (optional)

```bash
aiir --range origin/main..HEAD --pretty
```

Receipts every commit on your feature branch in one pass.

## What you get

- A `.aiir/receipts.jsonl` file tracking every receipted commit
- Each receipt records: commit SHA, author, files changed, and AI involvement
- Tamper-evident — the content hash breaks if anything is edited
- No account, no server, no network — everything stays local

## What you don't get (yet)

- **No signing** — unsigned receipts prove integrity but not provenance. Anyone
  who runs `aiir` on the same commit can produce an equivalent receipt.
- **No CI gate** — receipts are informational, not enforced.
- **No detection of undeclared AI** — AIIR records what's in commit metadata.
  Copilot Chat sessions without `Co-authored-by` trailers are not detected.

When you need signing or CI enforcement, see the
[OSS Maintainer guide](guide-oss-maintainer.md).

---

## Quick reference

| Task | Command |
|------|---------|
| Receipt last commit | `aiir --pretty` |
| Receipt a branch | `aiir --range main..HEAD --pretty` |
| Verify receipts | `aiir --verify .aiir/receipts.jsonl --explain` |
| Ledger stats | `aiir --stats` |
| Initialize `.aiir/` | `aiir --init` |
| README badge | `aiir --badge` |
