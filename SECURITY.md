# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.7.x   | ✅ Active (current) |
| 1.6.x   | ✅ Security fixes |
| 1.5.x   | ✅ Security fixes |
| 1.4.x   | ✅ Security fixes |
| < 1.4.0 | ❌ Unsupported — upgrade to 1.7.x |

## Reporting a Vulnerability

**This is a security-critical tool.** We take every report seriously.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, report vulnerabilities via:

- **Email**: [noah@invariantsystems.io](mailto:noah@invariantsystems.io)
- **Subject prefix**: `[VULN] aiir: <brief description>`

### What to include

1. Description of the vulnerability
2. Steps to reproduce
3. Affected versions
4. Severity assessment (if known)
5. Suggested fix (if any)

### Response timeline

| Stage | Target |
|-------|--------|
| Acknowledgment | 24 hours |
| Initial triage | 48 hours |
| Fix for Critical/High | 7 days |
| Fix for Medium/Low | 30 days |
| Public disclosure | After fix is released |

### Scope

The following are in scope:

- **aiir/cli.py**: public API shell and CLI entry point
- **aiir/_core.py**: constants, encoding helpers, git operations, hashing
- **aiir/_detect.py**: AI signal detection and commit metadata parsing
- **aiir/_receipt.py**: receipt building, generation, formatting, writing
- **aiir/_verify.py**: receipt content-addressed integrity verification
- **aiir/_verify_cbor.py**: canonical CBOR sidecar verification
- **aiir/_verify_release.py**: release-scoped verification and Verification Summary Attestation
- **aiir/_schema.py**: receipt schema validation
- **aiir/_canonical_cbor.py**: deterministic Canonical CBOR encoding
- **aiir/_sign.py**: Sigstore signing and verification
- **aiir/_ledger.py**: append-only JSONL ledger with auto-index
- **aiir/_stats.py**: badge, stats dashboard, policy checks
- **aiir/_github.py**: GitHub Actions integration
- **aiir/_gitlab.py**: GitLab CI/CD integration
- **aiir/mcp_server.py**: MCP server for AI assistants (path-restricted, error-sanitized)
- **action.yml**: GitHub Actions composite action
- **Receipt integrity**: content-addressed hashing chain
- **Output injection**: GitHub Actions output/summary manipulation
- **Supply chain**: dependency pinning and integrity

### Out of scope

- AI detection bypass (this is a known limitation of heuristic detection; see README)
- Issues in upstream dependencies (`actions/setup-python`, `actions/upload-artifact`, etc.)
- Denial of service via extremely large repositories (mitigated by `--max-count` limit)

## Security Design

### Threat model

This tool processes untrusted input from:

1. **Git commit metadata**: author names, emails, subjects, message bodies
2. **GitHub Actions inputs**: `commit-range`, `ai-only`, `output-dir`
3. **Diff content**: full diffs are hashed but not stored in receipts

### Security properties

- **Content-addressed receipts**: The `receipt_id` and `content_hash` are derived from SHA-256 of the canonical JSON receipt core. Modifying any field invalidates both.
- **Sigstore keyless signing** (optional): Receipts can be cryptographically signed using Sigstore, providing non-repudiation and a public transparency log entry (Rekor). Uses OIDC keyless signing, so no key management is required. In GitHub Actions, ambient credentials are used automatically when `id-token: write` is set.
- **NUL-byte delimited parsing**: Git metadata fields are parsed using `%x00` delimiters to prevent field injection via pipes or other characters in author names.
- **Ref validation**: All user-provided git refs are validated to reject option-like strings (e.g., `--all`), preventing git argument injection.
- **Heredoc output pattern**: GitHub Actions outputs use the heredoc delimiter pattern to prevent output injection via multiline values.
- **Pinned dependencies**: All action `uses:` dependencies are pinned to full commit SHAs, not mutable version tags. Pip dependencies (Sigstore) are installed with `--require-hashes` from a pinned requirements file with SHA-256 digests.
- **Markdown sanitization**: Commit subjects in step summaries are sanitized to prevent image beacon, phishing link, and HTML injection.
- **Zero dependencies**: Only Python standard library. No supply chain attack surface from pip packages.
- **PEP 740 digital attestations**: Every wheel and sdist published to PyPI includes in-toto-style digital attestations (SLSA provenance + PyPI Publish predicates), cryptographically signed via short-lived OIDC identities from Trusted Publishing. No static keys to compromise.
- **SLSA provenance**: GitHub Actions `attest-build-provenance` generates SLSA provenance attestations for both wheel and sdist, binding each artifact to the specific build invocation.
- **PyPI Integrity API verification**: Post-publish CI verifies that attestations are retrievable via PyPI's Integrity API (`GET /integrity/aiir/<version>/<file>/provenance`). A standalone verification script (`scripts/verify-pypi-provenance.py`) is provided for consumers. The script operates at two levels: **structural** (stdlib only: validates that attestation bundles are present and that `publisher.repository`, `publisher.workflow`, `publisher.environment`, and predicate type all match the expected AIIR values) and **cryptographic** (requires `pip install aiir[sign]`: additionally performs real Sigstore bundle verification enforcing the OIDC identity, subject artifact digest, and Rekor log binding). Without the optional extras the script checks attestation presence and signer-identity fields only; it does NOT verify any cryptographic signature.
- **Trusted Publishing (OIDC)**: PyPI uploads use GitHub's OIDC identity provider, with short-lived, scoped tokens instead of long-lived API tokens. No `PYPI_TOKEN` secret to rotate or leak.

### Verifying AIIR release provenance

Consumers can verify that any AIIR release was built by the official CI pipeline.

**Verification levels for `verify-pypi-provenance.py`:**

- **Structural** (stdlib only, no extra install): Checks attestation presence,
  validates that `publisher.repository == invariant-systems-ai/aiir`,
  `publisher.workflow == publish.yml`, `publisher.environment == pypi`, and
  that the expected publish/v1 predicate type is present. Does NOT verify
  any cryptographic signature.
- **Cryptographic** (`pip install aiir[sign]`): Additionally performs real
  Sigstore bundle verification enforcing the OIDC identity, the subject
  artifact digest, and the Rekor transparency-log binding. A fabricated or
  misattributed bundle fails closed.

```bash
# One-command public release-evidence gate (strict by default)
python scripts/verify-release-evidence.py

# Structural check only (stdlib, no extra deps)
python scripts/verify-pypi-provenance.py

# Verify a specific version (structural)
python scripts/verify-pypi-provenance.py 1.7.0

# Strict mode -- fail if any artifact lacks valid attestations (structural)
python scripts/verify-pypi-provenance.py --strict

# Cryptographic check (requires aiir[sign] or pip install pypi-attestations sigstore)
pip install aiir[sign]
python scripts/verify-pypi-provenance.py --strict
```

The `verify-release-evidence.py` wrapper is the simplest public CI entrypoint for
release provenance coverage. It calls the provenance verifier in strict mode and
checks published attestations via PyPI's Integrity API along with the GitHub
release attestation surface. It is not an offline verifier; local offline receipt
checks still use `aiir --verify`.

Alternatively, query the PyPI Integrity API directly:

```bash
# Fetch attestations for a specific file
curl -s https://pypi.org/integrity/aiir/1.7.0/aiir-1.7.0-py3-none-any.whl/provenance | python3 -m json.tool
```

## Automation secrets

The AIIR project minimises long-lived secrets through OIDC Trusted Publishing
(PyPI), Sigstore keyless signing, and the automatic `GITHUB_TOKEN`. The
remaining long-lived automation credentials are managed in two layers:

1. Canonical local vault: `~/.config/kaleidos/secrets.env`
2. GitHub Actions delivery plane: environment `automation-secrets`

Use the non-secret catalog in `.github/automation-secrets.json` plus:

```bash
python3 scripts/sync_ci_secrets.py --check
python3 scripts/sync_ci_secrets.py --apply
```

This keeps one canonical source of truth on the workstation while making CI
repairable from a single sync command.

| Secret | Type | Delivery plane | Used by |
|--------|------|----------------|---------|
| `GITLAB_TOKEN` | GitLab PAT | `automation-secrets` | `.github/workflows/sync.yml` |
| `NPM_TOKEN` | npm granular token | `automation-secrets` | `.github/workflows/publish.yml`, `.github/workflows/release-recovery.yml` |
| `WEBSITE_DISPATCH_TOKEN` | GitHub fine-grained PAT | `automation-secrets` | publish, release recovery, dogfood website dispatch |
| `TRAFFIC_TOKEN` | GitHub PAT | `automation-secrets` | `.github/workflows/traffic-archive.yml` |
| `VSCE_PAT` | Azure DevOps Marketplace PAT | `automation-secrets` | VS Code Marketplace publish jobs |
| `OVSX_PAT` | Open VSX token | `automation-secrets` | Optional Open VSX publish |

**Update procedure:**

1. Add or replace the value in the canonical vault file.
2. Run `python3 scripts/sync_ci_secrets.py --apply`.
3. Trigger the relevant workflow to verify the new token works.
4. If the live workflow still depends on a compatibility repo secret, use `python3 scripts/sync_ci_secrets.py --apply --sync-repo-bridge` until that bridge is removed.

**Design intent:** If any secret expires or is revoked, the failure mode is
explicit and repairable. The operator fixes the canonical vault once, reruns
the sync script, and the GitHub environment is restored without hand-editing
multiple secret stores.

## Acknowledgments

We gratefully acknowledge security researchers who report vulnerabilities responsibly.

- [@EQSTLab](https://github.com/EQSTLab) for responsibly reporting the VS Code extension workspace-controlled CLI path issue.
