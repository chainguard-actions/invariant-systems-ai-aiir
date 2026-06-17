<!-- markdownlint-disable MD041 -->
<p align="center">
  <a href="https://invariantsystems.io">
    <img src="docs/logo.svg" alt="Invariant Systems" width="120" height="120">
  </a>
</p>

# AIIR — AI Integrity Receipts

> **STATUS: public OSS ecosystem surface (2026-04-26).** AIIR is an open-source
> authorship-provenance and agent-evidence project. It is a public,
> independently verifiable OSS surface, not a hosted control plane or private
> reviewer service. The focus is portable receipts, in-toto wrappers, public
> policy presets, and the emerging AIIR agent-receipt profile draft.

**The missing provenance layer for AI-assisted code.**

Your team uses AI to write code. In six months, someone — an auditor, a security review, a regulator, a customer — will ask: *which parts of this codebase were AI-generated, and can you prove it?*

Git history can't answer that. `Co-authored-by` trailers are inconsistent and easy to strip. Policy documents aren't machine-verifiable. Today, most AI involvement in code leaves no durable, tamper-evident trace.

AIIR closes that gap. It generates deterministic, content-addressed receipts for commits with declared AI involvement, and verifies them anywhere — locally, in CI, or offline — without trusting a central service. Zero dependencies. Apache 2.0.

[![PyPI](https://img.shields.io/pypi/v/aiir?color=blue)](https://pypi.org/project/aiir/)
[![CI](https://github.com/invariant-systems-ai/aiir/actions/workflows/ci.yml/badge.svg)](https://github.com/invariant-systems-ai/aiir/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)](https://github.com/invariant-systems-ai/aiir)
[![Website](https://img.shields.io/badge/Website-invariantsystems.io-blue)](https://invariantsystems.io)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-AIIR-blue?logo=github)](https://github.com/marketplace/actions/aiir-ai-integrity-receipts)
[![GitLab CI/CD Catalog](https://img.shields.io/badge/GitLab-CI%2FCD%20Catalog-orange?logo=gitlab)](https://gitlab.com/explore/catalog/invariant-systems/aiir)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/invariant-systems-ai/aiir/badge)](https://scorecard.dev/viewer/?uri=github.com/invariant-systems-ai/aiir)
[![GitHub stars](https://img.shields.io/github/stars/invariant-systems-ai/aiir?style=social)](https://github.com/invariant-systems-ai/aiir/stargazers)

<p align="center">
  <img src="docs/demo.svg" alt="AIIR terminal demo — pip install aiir && aiir --pretty" width="720">
</p>

---

## Install → Generate → Verify

```bash
pip install aiir              # Python 3.9+, zero dependencies
cd your-repo
aiir --pretty                 # receipt your last commit
aiir --verify .aiir/receipts.jsonl   # verify nothing was tampered with
```

That's it. Your last commit now has a content-addressed receipt in `.aiir/receipts.jsonl`. Run it again on the same commit: same receipt, zero duplicates. Add CI and signing later only if you need stronger release evidence.

If you want the shortest anomaly instead of the full product tour, start with [examples/verify-pass-strict-fail/](examples/verify-pass-strict-fail/): the same receipt verifies cleanly in both directories, but the unsigned directory still fails `--policy strict` until the matching `.sigstore` sidecar is present.

### What just happened?

```text
┌─ Receipt: g1-a3f8b2c1d4e5f6a7...
│  Commit:  c4dec85630
│  Author:  Jane Dev <jane@example.com>
│  Files:   4 changed
│  AI:      YES (copilot)
│  Hash:    sha256:7f3a8b...
└──────────────────────────────────────
```

AIIR read your commit metadata, canonicalized the declared AI context, and produced a **content-addressed receipt**. Change one byte in the receipt core and verification fails — that's the tamper-evidence.

Without signing, a receipt proves **integrity** (nothing was altered). Add [Sigstore signing](#sigstore-signing) in CI for **authenticity** (proving *who* generated it).

Verification does not require trusting AIIR or a hosted service. Receipts are plain JSON and can be checked anywhere a verifier runs.

---

## What AIIR does — and does not do

AIIR does three things at its core:

- Records **declared** AI involvement in commit metadata
- Generates deterministic, tamper-evident receipts for those commits
- Verifies those receipts independently across local, CI, and offline workflows

AIIR does **not** attempt to prove hidden AI usage.

It does not claim to detect every undeclared use of Copilot, ChatGPT, Claude, Cursor, or any other tool. Its job is narrower and stronger: make declared AI involvement verifiable and tamper-evident.

---

## Why not just trailers or git notes?

You could track AI involvement with `Co-authored-by` trailers or ADRs — and AIIR is compatible with that. The difference:

- **Machine-verifiable** — receipts have a deterministic hash. Change one byte and verification fails.
- **Consistent** — same format across CLI, editor, CI, and AI assistants instead of ad-hoc free text.
- **Optional signing** — add Sigstore in CI when you need cryptographic non-repudiation.

Trailers are the baseline. AIIR makes that baseline verifiable.

---

## Declared Provenance and Optional Signal Enrichment

AIIR records what is **declared** in commit metadata, not what is hidden.

Detection signals are optional enrichment. They help normalize and classify declared context, but they are not authoritative proof of hidden AI usage.

**Catches:** `Co-authored-by: Copilot` trailers, bot authors (Dependabot, Renovate), `Assisted-by:` and `Generated-by:` trailers, 48 known AI-tool signals, and Unicode evasion attempts (TR39 confusable resolution, NFKC normalization).

**Does not catch:** Copilot inline completions (no trailer), copy-paste from ChatGPT, agent-mode sessions (Copilot Chat, Claude Code, Cursor Agent), squash merges that strip trailers, or amended commits.

This repo was built heavily with assistant help, yet the checked-in `.aiir` snapshot on `main` still skews heavily `human` because chat-based assistants like Copilot Chat do not leave durable declaration signals. The receipt format is faithfully recording *declared* signals; closing that declaration gap is exactly the wedge the AIIR agent-receipt profile addresses.

See [THREAT_MODEL.md](THREAT_MODEL.md) for the full STRIDE/DREAD analysis, and the [detection table](#detection-details) below for every signal.

---

## System Layers

AIIR is one kernel with trust layers around it, not a bundle of separate products.

- **Kernel** — deterministic receipts + independent verification
- **Assurance** — signing, policy enforcement, release evidence
- **Adapters** — CLI, GitHub Action, GitLab CI, VS Code, MCP, browser verification
- **Enrichment** — AI signal detection, heuristics, metadata extraction

Everything above emits or verifies the same receipt format.

---

## Where AIIR fits in the supply chain

AIIR is not a replacement for SLSA, in-toto, or SCITT. It fills a specific gap: **authorship-level provenance** — recording *who or what* produced a code change, before it enters the build pipeline.

| System | Layer | What it proves | Where AIIR fits |
|--------|-------|---------------|-----------------|
| [SLSA](https://slsa.dev) | Build provenance | *How* an artifact was built, from which source | AIIR receipts feed SLSA as source-level attestations |
| [in-toto](https://in-toto.io) | Supply chain attestation | That each step in a layout was performed correctly | AIIR wraps receipts as in-toto Statements (`--in-toto`) |
| [SCITT](https://scitt.io) | Transparency ledger | That a claim was registered in a tamper-evident log | AIIR receipts are valid SCITT claims (content-addressed, signable) |
| [Sigstore](https://sigstore.dev) | Signing infrastructure | *Who* signed an artifact (identity binding) | AIIR uses Sigstore for receipt signing (`--sign`) |
| [OpenSSF Scorecard](https://scorecard.dev) | Project health | Security posture of an OSS project | Orthogonal — AIIR tracks per-commit AI provenance, not project posture |
| Git trailers | Commit metadata | Free-text annotation | AIIR makes trailers machine-verifiable and tamper-evident |

**Think of it this way:** Git records *that* a change happened. SLSA records *how* the artifact was built. AIIR records *what* produced the change — human, AI-assisted, or bot — with a verifiable receipt.

For narrow public adapter notes that fit AIIR into existing attestation, graph, and
policy ecosystems without overclaiming standards status, see [docs/ecosystem.md](docs/ecosystem.md)
and the public hub at <https://invariantsystems.io/ecosystem/>.

Repo-local adapter notes are available for [GUAC](contrib/guac/README.md),
[Witness](contrib/witness/README.md), and [AMPEL policy](contrib/ampel/README.md).

For the public draft of the AIIR agent-receipt profile, see
[docs/agent-receipt-contract.md](docs/agent-receipt-contract.md).

For non-commit artifacts such as evaluation plans, manifests, benchmark matrices,
or public chronology baselines, AIIR can also emit a generic commitment receipt
over files, directories, or declared digests. See
[docs/commitment-receipts.md](docs/commitment-receipts.md).

### Commitment receipts beyond git commits

```bash
aiir \
  --commitment-artifact plan.json \
  --commitment-name nisq-eval-plan \
  --commitment-summary "Declared evaluation plan before rerun" \
  --output .receipts \
  --sign
```

This produces a content-addressed AIIR receipt for arbitrary artifacts, then
optionally signs it with Sigstore so the resulting JSON can be anchored in
Rekor-backed chronology the same way commit receipts are.

For concrete public fixtures, see
[examples/commitment-receipt-bundle/](examples/commitment-receipt-bundle/) for
a signed digest-binding example and
[examples/commitment-directory-bundle/](examples/commitment-directory-bundle/)
for a signed directory-binding example, each with a matching Sigstore bundle
and a tampered negative case.

---

## Next steps: pick your path

Once the CLI works for you, add whichever surface fits your workflow:

### VS Code

Install the [AIIR extension](https://marketplace.visualstudio.com/items?itemName=invariant-systems.aiir) if you want editor-side inspection and local receipt workflows in VS Code. The CLI and CI/CD integrations are the primary release surfaces today; the extension is an optional convenience layer.

### CI/CD

```yaml
# GitHub Actions — one line (signing on by default)
- uses: invariant-systems-ai/aiir@v1
  with:
    output-dir: .receipts/
```

```yaml
# GitLab CI/CD Catalog — one line
include:
  - component: gitlab.com/invariant-systems/aiir/receipt@1
```

See [GitHub Action details](#github-action-details), [GitLab CI details](#gitlab-ci-details), or [other CI platforms](#more-cicd-platforms) (Azure, CircleCI, Bitbucket, Jenkins, Docker).

### AI assistants via MCP

```json
{
  "mcpServers": {
    "aiir": { "command": "aiir-mcp-server", "args": ["--stdio"] }
  }
}
```

Works with Claude, Copilot, Cursor, Continue, Cline, and Windsurf. Your assistant generates receipts automatically after writing code.

### Adoption guides

| Guide | For |
|-------|-----|
| [Solo developer](docs/guide-solo-developer.md) | Local receipting, pre-commit hook, no CI needed |
| [OSS maintainer](docs/guide-oss-maintainer.md) | Signed CI receipts, policy gates, contributor guidelines |
| [Security team](docs/guide-security-team.md) | Independent verification, trust tiers, compliance integration |
| [GitLens integration](docs/gitlens-integration.md) | AI commit composition + verifiable AIIR provenance |

### Fast operator layer

| Doc | Use it when you need to answer... |
|-----|----------------------------------|
| [Operator model](docs/operator-model.md) | What can fail? What blocks it? What do I do next? |
| [Trap-case catalog](docs/trap-case-catalog.md) | Which technically-green states still create operational or business risk? |
| [Residual risk boundary](docs/residual-risk.md) | What can AIIR decide safely on its own, and what still needs a human owner? |

See also: [Verify AIIR independently](docs/verify-independently.md) — verify receipts without trusting AIIR, using only standard tools.

---

## Proof points

Everything below is verifiable. No testimonials-behind-a-login — just public artifacts you can audit yourself.

These proof surfaces support the kernel. They do not replace it.

| Proof | What it proves | Verify it |
|-------|---------------|-----------|
| **This repo receipts itself** | Dogfood — every push to `main` runs AIIR and publishes signed receipts to the public `receipts` branch | [receipts branch](https://github.com/invariant-systems-ai/aiir/tree/receipts), [dogfood workflow](https://github.com/invariant-systems-ai/aiir/actions/workflows/dogfood.yml) |
| **2,499 collected tests, 100% coverage** | Every release passes Python 3.9–3.13 × Ubuntu/macOS/Windows | [CI runs](https://github.com/invariant-systems-ai/aiir/actions/workflows/ci.yml) |
| **97 stable commit-receipt conformance test vectors** | Third-party implementors can verify stable hashing, adversarial handling, Unicode evasion, and canonicalization for the AIIR commit-receipt spec | [schemas/test_vectors.json](schemas/test_vectors.json), [conformance-manifest.json](schemas/conformance-manifest.json) |
| **3 agent-receipt draft vectors** | The AIIR agent-receipt profile draft already has machine-readable canonicalization and `record_id` derivation examples | [schemas/test-vectors/agent_receipt_vectors.v0.1.json](schemas/test-vectors/agent_receipt_vectors.v0.1.json) |
| **150+ documented security controls** | Per-element STRIDE analysis, DREAD risk scoring, and attack trees — published in full | [THREAT_MODEL.md](THREAT_MODEL.md) |
| **Release evidence on every release** | PyPI artifacts, GitHub provenance bundles, the release SBOM, and a Rekor-backed release manifest are bound into a public verification surface | `python scripts/verify-release-evidence.py 1.6.0` |
| **OpenSSF Scorecard** | Automated security health assessment | [Scorecard](https://scorecard.dev/viewer/?uri=github.com/invariant-systems-ai/aiir) |
| **CycloneDX SBOM** | Machine-readable bill of materials on every GitHub Release | [Latest release](https://github.com/invariant-systems-ai/aiir/releases/latest) → `aiir-sbom.cdx.json` |
| **Zero runtime dependencies** | Nothing to compromise | `pip install aiir && pip show aiir` |
| **Browser verifier** | Client-side receipt verification — no upload, no account | [invariantsystems.io/verify](https://invariantsystems.io/verify) |

See [docs/case-studies/aiir-self-dogfood.md](docs/case-studies/aiir-self-dogfood.md)
for the public dogfood walkthrough behind the first proof row.

---

## Trust tiers

| Tier | What you get | Use when |
|------|-------------|----------|
| **Unsigned** (`sign: false`) | Tamper-evident — hash integrity detects modification | Local dev, internal audit trails |
| **Inference-Bound** | Model output cryptographically committed via hash chain | Verifying AI inference provenance |
| **Signed** (`sign: true`, default in CI) | Authenticity — Sigstore binds the receipt to an OIDC identity | CI/CD compliance, SOC 2 evidence |
| **Enveloped** (`--in-toto --sign`) | Signed + in-toto Statement v1 envelope | SLSA provenance; designed to support use as evidence under frameworks like the EU AI Act |

---

## Verification pipeline

```text
git commit → AIIR receipt → Sigstore signing → Policy evaluation → VSA → CI gate
```

For developers: add `aiir` to CI and get a pass/fail check.
For security teams: get policy-evaluated results as signed attestations.
For auditors: query the JSONL ledger — every claim is cryptographically verifiable.

```bash
# Verify a receipt with explanation
aiir --verify receipt.json --explain

# Verify an inference receipt (auto-detected by field signature)
aiir --verify inference_receipt.json

# Evaluate all receipts against policy, emit a Verification Summary Attestation
aiir --verify-release --policy strict --emit-vsa
```

---

## CLI reference

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

<details>
<summary><strong>Full CLI reference</strong></summary>

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

# Initialize .aiir/ directory
aiir --init                        # scaffolds receipts.jsonl, index, config, .gitignore
aiir --init --policy strict        # also creates policy.json

# Review receipts — human attestation
aiir --review HEAD
aiir --review abc123 --review-outcome rejected --review-comment "needs refactor"

# Commit trailers
aiir --trailer                     # prints AIIR-Receipt, AIIR-Type, AIIR-AI, AIIR-Verified

# Policy engine
aiir --policy-init strict          # creates .aiir/policy.json
aiir --check --policy strict       # CI gate: fail if policy violated
aiir --check --max-ai-percent 50   # fail if >50% commits are AI-authored

# Ledger utilities
aiir --stats                       # dashboard of ledger statistics
aiir --badge                       # shields.io badge Markdown
aiir --export backup.json          # portable JSON bundle

# Privacy — omit file paths from receipts
aiir --redact-files --namespace acme-corp

# Native GitLab CI mode
aiir --gitlab-ci --output .receipts/
aiir --gitlab-ci --gl-sast-report
```

</details>

---

## Reference

<details id="detection-details">
<summary><strong>Detection details</strong></summary>

### Declared AI assistance

| Signal | Examples |
|--------|----------|
| **Copilot** | `Co-authored-by: Copilot`, `Co-authored-by: GitHub Copilot` |
| **ChatGPT** | `Generated by ChatGPT`, `Co-authored-by: ChatGPT` |
| **Claude** | `Generated by Claude`, `Co-authored-by: Claude` |
| **Cursor** | `Generated by Cursor`, `Co-authored-by: Cursor` |
| **Amazon Q / CodeWhisperer** | `amazon q`, `codewhisperer`, `Co-authored-by: Amazon Q` |
| **Devin** | `Co-authored-by: Devin`, `devin[bot]` |
| **Gemini** | `gemini code assist`, `google gemini`, `gemini[bot]` |
| **GitLab Duo** | `gitlab duo`, `duo code suggestions`, `duo chat`, `duo enterprise` |
| **Tabnine** | `tabnine` in commit metadata |
| **Aider** | `aider:` prefix in commit messages |
| **Generic markers** | `AI-generated`, `LLM-generated`, `machine-generated` |
| **Git trailers** | `Assisted-by:`, `Generated-by:`, `AI-assisted:`, `Tool:` |

### Automation / bot activity

| Signal | Examples |
|--------|----------|
| **Dependabot** | `dependabot[bot]` as author |
| **Renovate** | `renovate[bot]` as author |
| **Snyk** | `snyk-bot` as author |
| **CodeRabbit** | `coderabbit[bot]` as author |
| **GitHub Actions** | `github-actions[bot]` as author |
| **GitLab Bot** | `gitlab-bot` as author |
| **DeepSource** | `deepsource[bot]` as author |

Since v1.0.4, bot and AI signals are fully separated. A Dependabot commit gets `is_bot_authored: true` and `authorship_class: "bot"`, **not** `is_ai_authored: true`.

### Detection internals

Homoglyph detection uses the full [Unicode TR39 confusable map](https://www.unicode.org/reports/tr39/) — 669 single-codepoint → ASCII mappings across 69 scripts. Combined with NFKC normalization, this covers all single-character homoglyphs documented by the Unicode Consortium. Multi-character confusable sequences are not covered — see S-02 in the threat model.

</details>

<details id="github-action-details">
<summary><strong>GitHub Action details</strong></summary>

### Full workflow (signed, with PR integration)

```yaml
name: AIIR
on:
  push:
    tags-ignore: ['**']
  pull_request:

permissions:
  id-token: write
  contents: read
  checks: write
  pull-requests: write

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

Signing is **on by default**. Artifacts uploaded automatically when `output-dir` is set.

**Hardened (pin to full SHA):**

```yaml
      - uses: invariant-systems-ai/aiir@a54fe440a2be18fe51ad30149f1bbab944d578e5  # v1
```

**Unsigned (no permissions needed):**

```yaml
      - uses: invariant-systems-ai/aiir@v1
        with:
          sign: false
```

**Automatic PR integration** (when `GITHUB_TOKEN` is available):

- Creates an `aiir/verify` Check Run (pass/fail status on every PR)
- Posts a receipt summary comment (idempotent, no spam)

### Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `ai-only` | Only receipt AI-authored commits | `false` |
| `commit-range` | Specific commit range (e.g., `main..HEAD`) | Auto-detected |
| `output-dir` | Directory to write receipt JSON files | *(log only)* |
| `sign` | Sign receipts with Sigstore | `true` |

### Outputs

| Output | Description |
|--------|-------------|
| `receipt_count` | Number of receipts generated |
| `ai_commit_count` | Number of AI-authored commits detected |
| `signed_receipt_count` | Number of signed receipts generated |
| `unsigned_receipt_count` | Number of unsigned receipts generated |
| `receipts_json` | Full JSON array (set to `"OVERFLOW"` if >1 MB) |
| `receipts_overflow` | `"true"` when truncated |

> ⚠️ **Security note on `receipts_json`**: Contains commit metadata which may include shell metacharacters. **Never** interpolate directly into `run:` steps via `${{ }}`. Write to a file instead.

### Example: PR Comment with AI Summary

```yaml
      - uses: invariant-systems-ai/aiir@v1
        id: receipt
        with:
          output-dir: .receipts/

      - name: Comment on PR
        if: steps.receipt.outputs.ai_commit_count > 0
        uses: actions/github-script@v7
        with:
          script: |
            const count = '${{ steps.receipt.outputs.ai_commit_count }}';
            const total = '${{ steps.receipt.outputs.receipt_count }}';
            const signed = '${{ steps.receipt.outputs.signed_receipt_count }}';
            const unsigned = '${{ steps.receipt.outputs.unsigned_receipt_count }}';
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `🔐 **AIIR**: ${total} commits receipted, ${count} AI-authored, ${signed} signed, ${unsigned} unsigned.\n\nReceipts uploaded as build artifacts.`
            });
```

</details>

<details id="gitlab-ci-details">
<summary><strong>GitLab CI details</strong></summary>

**CI/CD Catalog component** (recommended — [browse in Catalog](https://gitlab.com/explore/catalog/invariant-systems/aiir)):

```yaml
include:
  - component: gitlab.com/invariant-systems/aiir/receipt@1
    inputs:
      stage: test
```

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `stage` | string | `test` | Pipeline stage |
| `version` | string | `1.6.0` | AIIR version from PyPI |
| `ai-only` | boolean | `false` | Only receipt AI-authored commits |
| `output-dir` | string | `.aiir-receipts` | Artifact output directory |
| `artifact-expiry` | string | `90 days` | Artifact retention |
| `sign` | boolean | `true` | Sigstore keyless signing (GitLab OIDC) |
| `gl-sast-report` | boolean | `false` | Generate SAST report for Security Dashboard |
| `approval-threshold` | number | `0` | AI% threshold for extra MR approvals (0 = off) |
| `extra-args` | string | `""` | Additional CLI flags |

**Legacy include** (no Catalog required):

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/invariant-systems-ai/aiir/v1.6.0/templates/gitlab-ci.yml'
```

**Self-hosted GitLab?** Mirror the repo and use `project:` instead:

```yaml
include:
  - project: 'your-group/aiir'
    ref: 'v1.6.0'
    file: '/templates/gitlab-ci.yml'
```

Customise via pipeline variables: `AIIR_VERSION`, `AIIR_AI_ONLY`, `AIIR_EXTRA_ARGS`, `AIIR_ARTIFACT_EXPIRY`. See [templates/gitlab-ci.yml](templates/gitlab-ci.yml).

</details>

<details id="more-cicd-platforms">
<summary><strong>More CI/CD platforms (Docker, Bitbucket, Azure, CircleCI, Jenkins)</strong></summary>

### Docker

```bash
docker run --rm -v "$(pwd):/repo" -w /repo invariantsystems/aiir --pretty
docker run --rm -v "$(pwd):/repo" -w /repo invariantsystems/aiir --ai-only --output .receipts/
```

Works in any CI system that supports container steps — Tekton, Buildkite, Drone, Woodpecker, etc.

### pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/invariant-systems-ai/aiir
    rev: v1.6.0
    hooks:
      - id: aiir
```

Runs **post-commit**. Customise with args: `["--ai-only", "--output", ".receipts"]`

### Bitbucket Pipelines

```yaml
pipelines:
  default:
    - step:
        name: AIIR Receipt
        image: python:3.11
        script:
          - pip install aiir
          - aiir --pretty --output .receipts/
        artifacts:
          - .receipts/**
```

Full template: [templates/bitbucket-pipelines.yml](templates/bitbucket-pipelines.yml)

### Azure DevOps

```yaml
steps:
  - task: UsePythonVersion@0
    inputs: { versionSpec: '3.11' }
  - script: pip install aiir && aiir --pretty --output .receipts/
    displayName: 'Generate AIIR receipt'
  - publish: .receipts/
    artifact: aiir-receipts
```

Full template: [templates/azure-pipelines.yml](templates/azure-pipelines.yml)

### CircleCI

```yaml
jobs:
  receipt:
    docker:
      - image: cimg/python:3.11
    steps:
      - checkout
      - run: pip install aiir && aiir --pretty --output .receipts/
      - store_artifacts:
          path: .receipts
```

Full template: [templates/circleci/config.yml](templates/circleci/config.yml)

### Jenkins

```groovy
pipeline {
    agent { docker { image 'python:3.11' } }
    stages {
        stage('AIIR Receipt') {
            steps {
                sh 'pip install aiir && aiir --pretty --output .receipts/'
                archiveArtifacts artifacts: '.receipts/**'
            }
        }
    }
}
```

Full template: [templates/jenkins/Jenkinsfile](templates/jenkins/Jenkinsfile)

</details>

<details id="sigstore-signing">
<summary><strong>Sigstore signing</strong></summary>

Sign receipts with [Sigstore](https://sigstore.dev) keyless signing for cryptographic non-repudiation:

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: invariant-systems-ai/aiir@v1
    with:
      output-dir: .receipts/
      sign: true
```

> **Fork PRs**: GitHub does not grant OIDC tokens to fork pull requests. AIIR will detect the missing credential and fail with a clear error rather than hanging.

Each receipt gets an accompanying `.sigstore` bundle (Fulcio certificate + Rekor transparency log entry + signature).

```bash
# Basic: checks signature is valid (any signer)
aiir --verify receipt.json --verify-signature

# Recommended: pin to a specific CI identity
aiir --verify receipt.json --verify-signature \
  --signer-identity "https://github.com/myorg/myrepo/.github/workflows/aiir.yml@refs/heads/main" \
  --signer-issuer "https://token.actions.githubusercontent.com"
```

> ⚠️ **Always use `--signer-identity` and `--signer-issuer` in production.**
> Without identity pinning, verification accepts any valid Sigstore signature.

Install signing support: `pip install aiir[sign]`

</details>

<details>
<summary><strong>Ledger — .aiir/ directory</strong></summary>

By default, `aiir` appends receipts to a local JSONL ledger:

```text
.aiir/
├── receipts.jsonl   # One receipt per line (append-only)
└── index.json       # Auto-maintained lookup index
```

- **One file to commit** — `git add .aiir/` is your entire audit trail
- **Auto-deduplicates** — re-running `aiir` on the same commit is a no-op
- **Git-friendly** — append-only JSONL means clean diffs and easy `git blame`
- **Queryable** — `jq`, `grep`, and `wc -l` all work naturally

| Flag | Behaviour |
|------|-----------|
| *(none)* | Append to `.aiir/receipts.jsonl` (default) |
| `--ledger .audit/` | Append to custom ledger directory |
| `--json` | Print JSON to stdout — no ledger write |
| `--jsonl` | Print JSON Lines to stdout — no ledger write |
| `--output dir/` | Write individual files to `dir/` — no ledger write |
| `--pretty` | Human-readable summary to stderr (combines with any mode) |

</details>

<details>
<summary><strong>Receipt format</strong></summary>

```json
{
  "type": "aiir.commit_receipt",
  "schema": "aiir/commit_receipt.v2",
  "receipt_id": "g1-a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4",
  "content_hash": "sha256:7f3a...",
  "timestamp": "2026-03-06T09:48:59Z",
  "commit": {
    "sha": "c4dec85630232666aba81b6588894a11d07e5d18",
    "author": { "name": "Jane Dev", "email": "jane@example.com" },
    "subject": "feat: add receipt generation to CI",
    "files_changed": 4
  },
  "ai_attestation": {
    "is_ai_authored": true,
    "signals_detected": ["message_match:co-authored-by: copilot"],
    "authorship_class": "ai_assisted",
    "detection_method": "heuristic_v2"
  }
}
```

**Content-addressed**: `receipt_id` is derived from SHA-256 of the canonical JSON. Change any field → hash changes → receipt invalid.

> **Receipt identity depends on repository provenance.**
> The `provenance.repository` field is part of the content hash. The same commit
> produces a different `receipt_id` if the remote URL changes (fork, rename, etc.).

</details>

<details>
<summary><strong>Release verification & VSA</strong></summary>

```bash
aiir --verify-release --receipts .receipts/ --policy strict --emit-vsa
```

Produces an [in-toto Statement v1](https://in-toto.io/Statement/v1) with a [Verification Summary Attestation](https://slsa.dev/verification_summary) predicate recording: verifier identity, policy digest, coverage metrics, and pass/fail result.

Policy presets: `strict` (hard-fail, signing required, zero unsigned receipts, max 50% AI), `balanced` (soft-fail, signing recommended), `permissive` (warn-only). Customise via `.aiir/policy.json`.

</details>

<details>
<summary><strong>Policy engine</strong></summary>

```bash
aiir --policy-init strict   # creates .aiir/policy.json
aiir --check --policy strict
aiir --check --max-ai-percent 50
```

| Preset | Enforcement | Signing | Max AI % | Use case |
|--------|-------------|---------|----------|----------|
| `strict` | Hard-fail | Required | 50% | Regulated industries, SOC 2; designed to support use as evidence under frameworks like the EU AI Act |
| `balanced` | Soft-fail | Recommended | 80% | Most teams |
| `permissive` | Warn-only | Optional | 100% | Early adoption |

</details>

<details>
<summary><strong>Agent attestation</strong></summary>

```bash
aiir --agent-tool copilot --agent-model gpt-4o --agent-context ide
```

Stored in `extensions.agent_attestation` (not part of the content hash). Six allowlisted keys: `tool_id`, `model_class`, `session_id`, `run_context`, `tool_version`, `confidence`.

</details>

<details>
<summary><strong>MCP server details</strong></summary>

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

</details>

<details>
<summary><strong>in-toto Statement wrapping</strong></summary>

```bash
aiir --in-toto --output .receipts/
aiir --sign --in-toto --output .receipts/
```

Current predicate type: `https://invariantsystems.io/predicates/aiir/commit_receipt/v2`. Compatible with SLSA verifiers, Sigstore policy-controller, Kyverno/OPA, and Tekton Chains. Legacy `aiir/commit_receipt.v1` receipts use the matching `/v1` predicate URI.

</details>

---

## Show AIIR in your README

Add a transparency badge so reviewers and auditors know your project receipts AI involvement:

```bash
aiir --badge        # auto-generates Markdown with your repo's AI %
```

Or copy a static badge:

```markdown
[![AIIR Receipts](https://img.shields.io/badge/AIIR-Receipted-blue)](https://github.com/invariant-systems-ai/aiir)
```

Preview: [![AIIR Receipts](https://img.shields.io/badge/AIIR-Receipted-blue)](https://github.com/invariant-systems-ai/aiir)

The `--badge` variant reads your ledger and shows the actual AI-assisted percentage. The static badge signals adoption without revealing stats.

---

## Specification & schemas

| Document | Purpose |
|----------|---------|
| [SPEC.md](SPEC.md) | Normative specification — canonical JSON, content addressing, verification |
| [SPEC_GOVERNANCE.md](SPEC_GOVERNANCE.md) | Change control, compatibility policy, extension registry |
| [docs/ecosystem.md](docs/ecosystem.md) | Where AIIR fits — comparison with SLSA, in-toto, SCITT, Sigstore |
| [docs/agent-receipt-contract.md](docs/agent-receipt-contract.md) | Public draft of the AIIR agent-receipt profile for IDEs, terminals, CI, and bots |
| [docs/agent-trace-interoperability.md](docs/agent-trace-interoperability.md) | Interoperability note for using AIIR as an optional tamper-evident evidence layer beside Agent Trace |
| [docs/sdks.md](docs/sdks.md) | SDK guide — Python reference implementation, JavaScript verifier, Rust CBOR crate |
| [docs/case-studies/aiir-self-dogfood.md](docs/case-studies/aiir-self-dogfood.md) | Public dogfood case study — AIIR generates receipts for AIIR itself |
| [schemas/commit_receipt.v2.schema.json](schemas/commit_receipt.v2.schema.json) | JSON Schema (draft 2020-12) for current receipt format |
| [schemas/agent_receipt_contract.v0.1.schema.json](schemas/agent_receipt_contract.v0.1.schema.json) | Draft JSON Schema for the AIIR agent-receipt profile |
| [schemas/test_vectors.json](schemas/test_vectors.json) | 25 core vectors in this file; 97 total across 8 stable commit-receipt vector files |
| [schemas/agent_receipt_vectors.v0.1.schema.json](schemas/agent_receipt_vectors.v0.1.schema.json) | JSON Schema for agent-receipt test vectors |
| [schemas/test-vectors/agent_receipt_vectors.v0.1.json](schemas/test-vectors/agent_receipt_vectors.v0.1.json) | 3 draft vectors for agent-receipt canonicalization and `record_id` derivation |
| [schemas/verification_summary.v1.schema.json](schemas/verification_summary.v1.schema.json) | JSON Schema for VSA predicate |
| [THREAT_MODEL.md](THREAT_MODEL.md) | STRIDE/DREAD threat model |
| [docs/tamper-detection.md](docs/tamper-detection.md) | Walkthrough — what happens when a receipt is modified |
| [docs/stability-contract.md](docs/stability-contract.md) | 1.0 stability contract — what freezes, what doesn't |
| [docs/verify-independently.md](docs/verify-independently.md) | Verify receipts without trusting AIIR |

---

## About

Built by [Invariant Systems, Inc.](https://invariantsystems.io) — Apache-2.0.

**Citing**: Use the **Cite this repository** button on GitHub or see [CITATION.cff](CITATION.cff).

**Trademarks**: "AIIR", "AI Integrity Receipts", and "Invariant Systems" are trademarks of Invariant Systems, Inc. See [TRADEMARK.md](TRADEMARK.md).

**Signed releases**: Every PyPI release uses [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) (OIDC) — no static API tokens. Each release is tied to a specific GitHub Actions run, commit SHA, and workflow file.

## Privacy

This Action contacts Chainguard's licensing server to verify authorization. Connection metadata (IP address, GitHub repository identifier, timestamp, and any metadata encoded in the auth token) is transmitted to Chainguard, Inc. even if authorization is denied in accordance with our [Privacy Notice](https://www.chainguard.dev/legal/privacy-notice)
