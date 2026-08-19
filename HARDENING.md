<!-- markdownlint-disable -->

# Hardening Report: invariant-systems-ai--aiir/v1.7.0

> This file was generated automatically by the hardening agent.

**Policy SHA:** `d636be7e43ef829af6e853da6b3c7566db9f72fe`

**Test Policy SHA:** `843adf9e4b8f85d0c08b27b9d0b09dd094b54702`

**Harden Agent Version:** `2`

Action **invariant-systems-ai--aiir/v1.7.0** was hardened automatically. 28 finding(s) were identified and resolved across 3 iteration(s).

## Findings Fixed

### script-injection (severity: high)

Sub-rule (a): ${{ inputs.receipt-dir }} is interpolated directly inside a run: shell command string (assigned to DIR variable). Additionally, ${{ steps.verify.outputs.failed }} and ${{ steps.verify.outputs.count }} are interpolated directly in the 'Post summary' run: block. Any expression inside a run: block is a script-injection risk regardless of context.

Locations:

- `.github/workflows/verify-receipts.yml:62`
- `.github/workflows/verify-receipts.yml:95`

### script-injection (severity: high)

Sub-rule (a): ${{ matrix.source }} and ${{ matrix.event }} are interpolated directly inside a run: shell command string passed as CLI arguments to python and as part of the --out-dir path. Example offending lines: `--source "${{ matrix.source }}"` and `--out-dir "pep740-preflight/${{ matrix.event }}-${{ matrix.source }}"`.

Locations:

- `.github/workflows/verify-attestations.yml:30`

### script-injection (severity: high)

Sub-rule (a): ${{ github.event.inputs.tag }} and ${{ github.event.inputs.source_ref }} are interpolated directly inside a run: shell command string. Offending lines: `RAW='${{ github.event.inputs.tag }}'` and `SOURCE='${{ github.event.inputs.source_ref }}'`. These are attacker-controlled workflow_dispatch inputs.

Locations:

- `.github/workflows/release-recovery.yml:17`

### script-injection (severity: high)

Sub-rule (a): ${{ github.event.release.tag_name }}, ${{ github.event.inputs.version }}, ${{ steps.ver.outputs.version }}, ${{ matrix.os }}, ${{ matrix.python }}, ${{ github.event_name }}, ${{ github.server_url }}, ${{ github.repository }}, and ${{ github.run_id }} are all interpolated directly inside run: shell command strings. Example: `if [[ -n "${{ github.event.release.tag_name }}" ]]` and `echo "Smoke test complete on ${{ matrix.os }} / Python ${{ matrix.python }}"`.

Locations:

- `.github/workflows/release-smoke.yml:30`
- `.github/workflows/release-smoke.yml:100`
- `.github/workflows/release-smoke.yml:107`

### script-injection (severity: high)

Sub-rule (a): ${{ needs.test.result }}, ${{ needs.fuzz.result }}, ${{ needs.lint.result }}, ${{ needs.coverage.result }}, ${{ needs.package.result }}, ${{ needs.version-check.result }}, ${{ needs.sdk-js.result }}, ${{ needs.sdk-rust.result }}, ${{ needs.sdk-vscode.result }} are all interpolated directly inside a run: shell command string in the ci-ok gate job. Example: `echo "test: ${{ needs.test.result }}"` and `if [[ "${{ needs.test.result }}" != "success" || ...`.

Locations:

- `.github/workflows/ci.yml:130`

### script-injection (severity: high)

Sub-rule (a): ${{ github.repository }} is interpolated directly inside run: shell command strings in multiple steps. Example: `EXISTING=$(gh issue list --repo "${{ github.repository }}" ...)` in the 'Create staleness issue' and 'Create failure issue' steps.

Locations:

- `.github/workflows/action-health.yml:130`
- `.github/workflows/action-health.yml:155`

### script-injection (severity: high)

Sub-rule (a): ${{ steps.receipt.outputs.receipt_count }} is interpolated directly inside a run: shell command string. Offending line: `EXPECTED="${{ steps.receipt.outputs.receipt_count }}"`.

Locations:

- `.github/workflows/dogfood.yml:80`

### script-injection (severity: high)

Sub-rule (a): ${{ steps.metadata.outputs.dependency-names }}, ${{ steps.metadata.outputs.update-type }}, ${{ steps.metadata.outputs.previous-version }}, and ${{ steps.metadata.outputs.new-version }} are interpolated directly inside run: shell command strings. Example: `echo "✅ Auto-approving ${{ steps.metadata.outputs.dependency-names }} (${{ steps.metadata.outputs.update-type }})"` and used in gh pr review/merge/comment body strings.

Locations:

- `.github/workflows/dependabot-auto-merge.yml:50`

### script-injection (severity: high)

Sub-rule (a): ${{ github.repository }} is interpolated directly inside run: shell command strings in multiple steps. Example: `MAIN_SHA=$(gh api "repos/${{ github.repository }}/git/ref/heads/main" ...)`, `CHECKS=$(gh api "repos/${{ github.repository }}/commits/...`)`, `gh release upload ... --repo "${{ github.repository }}"`, and `python3 scripts/emit_release_attest.py --repo "${{ github.repository }}" ...`.

Locations:

- `.github/workflows/publish.yml:40`
- `.github/workflows/publish.yml:60`
- `.github/workflows/publish.yml:120`
- `.github/workflows/publish.yml:145`
- `.github/workflows/publish.yml:175`

### script-injection (severity: high)

Sub-rule (a): ${{ github.repository }} is interpolated directly inside run: shell command strings in multiple steps. Example: `gh release view "$TAG_NAME" --repo "${{ github.repository }}"`, `gh api "repos/${{ github.repository }}/attestations/..."`, and `gh release upload ... --repo "${{ github.repository }}"`.

Locations:

- `.github/workflows/offline-rekor-release.yml:40`
- `.github/workflows/offline-rekor-release.yml:65`
- `.github/workflows/offline-rekor-release.yml:90`

### script-injection (severity: high)

Sub-rule (a): ${{ github.repository }} is interpolated directly inside run: shell command strings in the 'Create or update drift issue' step. Example: `EXISTING=$(gh issue list --repo "${{ github.repository }}" ...)` and `gh issue comment "$EXISTING" --repo "${{ github.repository }}" ...`.

Locations:

- `.github/workflows/sync.yml:130`

### script-injection (severity: high)

Sub-rule (a): ${{ needs.gitleaks.result }}, ${{ needs.sast.result }}, ${{ needs.semgrep.result }}, ${{ needs.lint.result }}, ${{ needs.dep-audit.result }}, and ${{ needs.license-check.result }} are all interpolated directly inside a run: shell command string in the security-ok gate job. Example: `echo "gitleaks: ${{ needs.gitleaks.result }}"` and `if [[ "${{ needs.gitleaks.result }}" != "success" ]] || ...`.

Locations:

- `.github/workflows/security.yml:100`

### github-env-injection (severity: high)

The 'Determine commit range' step writes the RANGE variable (derived from inputs.commit-range via INPUT_COMMIT_RANGE env var, and from github.event.pull_request.base.sha, github.event.pull_request.head.sha, github.event.before, github.event.after via env vars) to $GITHUB_OUTPUT using a heredoc with a random delimiter. The required sanitization step (printf '%s' "$RANGE" | tr -d '\n\r') is not applied immediately before the write. The input validation (grep -qE '[;&|$`\\]|[[:cntrl:]]') is not the required sanitization step.

Locations:

- `action.yml:107`

### github-env-injection (severity: high)

The 'Normalize tag input' step writes RAW (derived from ${{ github.event.inputs.tag }} directly interpolated in the run block) and SOURCE (derived from ${{ github.event.inputs.source_ref }} directly interpolated in the run block) to $GITHUB_OUTPUT without the required sanitization step (printf '%s' ... | tr -d '\n\r'). The regex validation for RAW only applies to the tag format; SOURCE is only checked for emptiness.

Locations:

- `.github/workflows/release-recovery.yml:17`

### github-env-injection (severity: high)

The 'Resolve target version' step writes VER (derived from ${{ github.event.release.tag_name }} and ${{ github.event.inputs.version }} directly interpolated in the run block) to $GITHUB_OUTPUT without the required sanitization step (printf '%s' ... | tr -d '\n\r').

Locations:

- `.github/workflows/release-smoke.yml:30`

### github-env-injection (severity: high)

The 'Determine target tag' step writes TAG (derived from INPUT_TAG env var which holds ${{ github.event.inputs.tag }}) to $GITHUB_OUTPUT without the required sanitization step (printf '%s' ... | tr -d '\n\r'). The value flows: ${{ github.event.inputs.tag }} → INPUT_TAG env var → TAG shell variable → echo "tag=$TAG" >> "$GITHUB_OUTPUT".

Locations:

- `.github/workflows/update-major-tag.yml:40`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/clusterfuzzlite.yml:20`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/codeql.yml:19`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/contribution-assessment.yml:16`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/dependabot-auto-merge.yml:18`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/dogfood.yml:17`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/pr-auto-merge.yml:18`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/publish.yml:20`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/pulse-suggestions.yml:18`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/release-recovery.yml:12`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/scorecard.yml:16`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/update-major-tag.yml:18`

### broad-permissions (severity: medium)

Top-level `permissions: read-all` grants overly broad read access to all GitHub API scopes. This should be replaced with specific minimal permissions scoped to what each job actually needs.

Locations:

- `.github/workflows/verify-receipts.yml:43`

## Iteration Notes

### Iteration 1

**Fixes applied:** script-injection, github-env-injection, broad-permissions

**Notes:**

Fixed all 28 findings across 16 workflow files and action.yml:

**Script-injection (12 findings):**
- verify-receipts.yml: Moved inputs.receipt-dir and steps.verify.outputs.* to env: blocks
- verify-attestations.yml: Moved matrix.source and matrix.event to env: block
- release-recovery.yml: Moved github.event.inputs.tag, github.event.inputs.source_ref, and github.repository to env: blocks
- release-smoke.yml: Moved github.event.release.tag_name, github.event.inputs.version, matrix.os, matrix.python, github.event_name, github.server_url, github.repository, github.run_id to env: blocks
- ci.yml: Moved all needs.*.result expressions to env: block
- action-health.yml: Moved github.repository to env: blocks in both affected steps
- dogfood.yml: Moved steps.receipt.outputs.receipt_count to env: block
- dependabot-auto-merge.yml: Moved all steps.metadata.outputs.* expressions to env: blocks
- publish.yml: Moved all github.repository usages in run: blocks to env: blocks (ci-gate, attach-dist, attach-sbom, upload-provenance, verify, release-attest, publish-vscode jobs)
- offline-rekor-release.yml: Moved github.repository to env: blocks in all three affected steps
- sync.yml: Moved github.repository to env: block
- security.yml: Moved all needs.*.result expressions to env: block

**GitHub-env-injection (4 findings):**
- action.yml: Added SAFE_RANGE=$(printf '%s' "$RANGE" | tr -d '\n\r') before writing to GITHUB_OUTPUT
- release-recovery.yml: Moved inputs to env: blocks and added sanitization before writing tag/version/source_ref to GITHUB_OUTPUT
- release-smoke.yml: Moved inputs to env: blocks and added sanitization before writing version to GITHUB_OUTPUT
- update-major-tag.yml: Added sanitization before writing tag to GITHUB_OUTPUT

**Broad-permissions (12 findings):**
- Replaced `permissions: read-all` with specific minimal permissions in: clusterfuzzlite.yml (contents:read, security-events:write), codeql.yml (contents:read, security-events:write, actions:read), contribution-assessment.yml (contents:read, issues:write, pull-requests:write, statuses:write), dependabot-auto-merge.yml (contents:read, pull-requests:read), dogfood.yml (contents:read), pr-auto-merge.yml (contents:read, pull-requests:write, statuses:write), publish.yml (contents:read), pulse-suggestions.yml (contents:write, pull-requests:write, issues:read), release-recovery.yml (contents:read), scorecard.yml (contents:read, security-events:write, id-token:write, actions:read), update-major-tag.yml (contents:read), verify-receipts.yml (contents:read, checks:write)

### Iteration 2

**Fixes applied:** github-env-injection

**Notes:**

Fixed the heredoc delimiter injection vulnerability in `.github/workflows/pulse-suggestions.yml` (Resolve issue context step, ~line 88). Replaced the fixed `EOF` delimiter used for `issue_title` and `issue_body` heredocs with cryptographically random delimiters generated via `openssl rand -hex 16` (prefixed with `ghadelimiter_`). Each heredoc now uses its own unique random delimiter, preventing an attacker from terminating the heredoc early by including a line that is exactly `EOF` in the issue body. Also switched from `echo` to `printf '%s\n'` for safer value output.

### Iteration 3

**Fixes applied:** script-injection

**Notes:**

Fixed two script-injection findings:
1. quality.yml (line ~180): Moved all 7 `${{ needs.*.result }}` expressions out of the `run:` block into an `env:` block with named variables (RESULT_TYPECHECK, RESULT_MARKDOWN_LINT, RESULT_LINK_CHECK, RESULT_SPELLING, RESULT_HADOLINT, RESULT_YAML_LINT, RESULT_SPDX_CHECK). Shell script now references plain env vars.
2. traffic-archive.yml (line ~75): Added `REPO: ${{ github.repository }}` to the step's `env:` block and replaced all four occurrences of `repos/${{ github.repository }}/...` with `"repos/$REPO/..."` in the shell script.

