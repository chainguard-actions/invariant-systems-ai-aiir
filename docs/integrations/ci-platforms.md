# CI/CD platform recipes

Full CI/CD integration for AIIR. The README has one-line setups for
[GitHub Actions and GitLab CI/CD](../../README.md#cicd); this page has the
complete configuration for both, Sigstore signing, and copy-paste recipes for
every other platform. Where a fuller template exists in the repo, it's linked.

## GitHub Actions

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
      - uses: invariant-systems-ai/aiir@a54fe440a2be18fe51ad30149f1bbab944d578e5  # pin: check the releases page for the current SHA of v1
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

## GitLab CI/CD

**CI/CD Catalog component** (recommended; [browse in Catalog](https://gitlab.com/explore/catalog/invariant-systems/aiir)):

```yaml
include:
  - component: gitlab.com/invariant-systems/aiir/receipt@1
    inputs:
      stage: test
```

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `stage` | string | `test` | Pipeline stage |
| `version` | string | `1.7.0` | AIIR version from PyPI |
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
  - remote: 'https://raw.githubusercontent.com/invariant-systems-ai/aiir/v1.7.0/templates/gitlab-ci.yml'
```

**Self-hosted GitLab?** Mirror the repo and use `project:` instead:

```yaml
include:
  - project: 'your-group/aiir'
    ref: 'v1.7.0'
    file: '/templates/gitlab-ci.yml'
```

Customise via pipeline variables: `AIIR_VERSION`, `AIIR_AI_ONLY`, `AIIR_EXTRA_ARGS`, `AIIR_ARTIFACT_EXPIRY`. See [templates/gitlab-ci.yml](../../templates/gitlab-ci.yml).

## Sigstore signing

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

## Docker

```bash
# Use the official image from GitHub Container Registry (pin the tag for reproducibility)
docker run --rm -v "$(pwd):/repo" -w /repo ghcr.io/invariant-systems-ai/aiir:1.6.0 --pretty
docker run --rm -v "$(pwd):/repo" -w /repo ghcr.io/invariant-systems-ai/aiir:1.6.0 --ai-only --output .receipts/
```

> The image is published to `ghcr.io/invariant-systems-ai/aiir:<version>`.
> There is no Docker Hub image.

Works in any CI system that supports container steps: Tekton, Buildkite, Drone, Woodpecker, etc.

## pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/invariant-systems-ai/aiir
    rev: v1.7.0
    hooks:
      - id: aiir
```

Runs **post-commit**. Customise with args: `["--ai-only", "--output", ".receipts"]`

## Bitbucket Pipelines

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

Full template: [templates/bitbucket-pipelines.yml](../../templates/bitbucket-pipelines.yml)

## Azure DevOps

```yaml
steps:
  - task: UsePythonVersion@0
    inputs: { versionSpec: '3.11' }
  - script: pip install aiir && aiir --pretty --output .receipts/
    displayName: 'Generate AIIR receipt'
  - publish: .receipts/
    artifact: aiir-receipts
```

Full template: [templates/azure-pipelines.yml](../../templates/azure-pipelines.yml)

## CircleCI

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

Full template: [templates/circleci/config.yml](../../templates/circleci/config.yml)

## Jenkins

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

Full template: [templates/jenkins/Jenkinsfile](../../templates/jenkins/Jenkinsfile)
