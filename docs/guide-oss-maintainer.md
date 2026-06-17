# Adoption Guide: OSS Maintainer

**Goal: signed receipts in CI, policy gate on PRs, release attestation.**

You maintain a public repository with contributors. You want verifiable evidence
of AI involvement on every merge, with Sigstore signing for non-repudiation and
a policy gate that blocks PRs that violate your rules.

---

## Step 1 — Add the GitHub Action

```yaml
# .github/workflows/aiir.yml
name: AIIR
on:
  push:
    tags-ignore: ['**']
  pull_request:

permissions:
  id-token: write      # Sigstore keyless signing
  contents: read
  checks: write        # aiir/verify check run on PRs

jobs:
  receipt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: invariant-systems-ai/aiir@v1
        with:
          output-dir: .receipts/
```

Signing is on by default. Every receipt gets a Sigstore bundle (Fulcio
certificate + Rekor transparency log entry).

### GitLab CI alternative

```yaml
# .gitlab-ci.yml
include:
  - component: gitlab.com/invariant-systems/aiir/receipt@1
    inputs:
      stage: test
```

## Step 2 — Initialize a policy

```bash
pip install aiir
aiir --init --policy balanced
```

This creates `.aiir/policy.json` with the `balanced` preset:

| Setting | Value |
|---------|-------|
| Enforcement | soft-fail (report, don't block) |
| Signing required | No (recommended) |
| Max AI percentage | 80% |

Commit `.aiir/policy.json` to your repo so every contributor and CI run uses
the same rules.

### Policy presets

| Preset | Best for | Max AI % | Signing |
|--------|----------|----------|---------|
| `permissive` | Early adoption, experiments | 100% | Optional |
| `balanced` | Most OSS projects | 80% | Recommended |
| `strict` | Regulated, SOC 2, EU AI Act | 50% | Required |

Switch presets:

```bash
aiir --policy-init strict
```

## Step 3 — Add a policy gate to CI

```yaml
      - uses: invariant-systems-ai/aiir@v1
        with:
          output-dir: .receipts/

      - name: Policy check
        run: pip install aiir && aiir --check --policy .aiir/policy.json
```

Or use `--max-ai-percent 80` for a quick threshold without a policy file.

## Step 4 — Release verification

Before cutting a release, verify all receipts against policy and emit a
Verification Summary Attestation (VSA):

```bash
aiir --verify-release --receipts .aiir/receipts.jsonl --policy balanced --emit-vsa
```

The VSA is a signed [in-toto Statement v1](https://in-toto.io/Statement/v1)
recording: verifier identity, policy digest, coverage metrics, and pass/fail.

## Step 5 — Communicate to contributors

Add to your `CONTRIBUTING.md`:

```markdown
## AI disclosure

This project uses [AIIR](https://github.com/invariant-systems-ai/aiir) to
generate verifiable receipts for commits with declared AI involvement.

If you use AI coding tools, please include a `Co-authored-by` trailer:

    Co-authored-by: Copilot <copilot@github.com>

AIIR detects these trailers automatically and records them in each receipt.
```

Add a badge to your README:

```bash
aiir --badge
```

## What you get

- Signed receipts on every push and PR
- `aiir/verify` check run visible as a status check (enforceable via branch protection)
- Policy evaluation against AI-usage thresholds
- Release-scoped attestations for downstream verification
- Transparency log entries for every signed receipt (public, auditable)

## What you don't get

- **Detection of undeclared AI** — AIIR records metadata signals, not hidden use
- **Automatic enforcement of contributor trailers** — AIIR records what's there,
  not what should be there. Convention enforcement is a social/tooling problem.
- **Offline signature verification** — Sigstore verification requires network
  access to check the transparency log. Unsigned receipts verify offline.

---

## Quick reference

| Task | Command |
|------|---------|
| Add to CI | `uses: invariant-systems-ai/aiir@v1` |
| Initialize policy | `aiir --init --policy balanced` |
| CI policy gate | `aiir --check --policy .aiir/policy.json` |
| Release verification + VSA | `aiir --verify-release --emit-vsa --policy balanced` |
| Verify a signed receipt | `aiir --verify receipt.json --verify-signature` |
| Pin signer identity | `--signer-identity <workflow-url> --signer-issuer https://token.actions.githubusercontent.com` |
