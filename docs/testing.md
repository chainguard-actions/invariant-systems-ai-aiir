# Testing AIIR

AIIR is public open source and security-critical. The testing workflow should be
easy for contributors to start, strict where the code is risky, and identical to
CI when a maintainer is preparing a branch for merge.

This guide explains the local test tiers and which ones are useful for different
kinds of changes. CI remains the final source of truth for pull requests.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -q --tb=short --ignore=tests/test_fuzz.py
```

On Windows, PowerShell works for focused `python -m pytest ...` commands. The
local CI script is Bash-based, so use WSL, Git Bash, or another POSIX-compatible
shell for `scripts/ci-local.sh`.

## Test tiers

| Tier | When to use it | Command |
|---|---|---|
| Focused tests | While editing one module or fixing one bug | `python -m pytest <tests> -q` |
| Unit suite | Before pushing most code changes | `python -m pytest tests/ -q --tb=short --ignore=tests/test_fuzz.py` |
| Fuzz tests | Serialization, detection, normalization, or parser changes | `python -m pytest tests/test_fuzz.py -q` |
| Coverage gate | Before merge-ready code review | `coverage run --source=aiir -m pytest tests/ --ignore=tests/test_fuzz.py -q --tb=short && coverage report --fail-under=100` |
| Required local CI | Maintainer pre-push and best local CI predictor | `scripts/ci-local.sh required` |
| Full local CI | Security-critical or release-adjacent changes | `scripts/ci-local.sh full` |
| Mutation gate | Verification and canonical encoding changes | `scripts/ci-local.sh mutation` |
| All local gates | Release-adjacent work or high-risk refactors | `scripts/ci-local.sh all` |

Small documentation-only pull requests may not need local test runs. In those
cases, say so in the PR testing section and let CI handle repository-wide
checks.

## Change-to-test map

| Changed surface | Start with | Also consider |
|---|---|---|
| `aiir/_core.py`, `aiir/_receipt.py` | `tests/test_core.py`, `tests/test_receipt.py` | `tests/test_schema.py`, `tests/test_fuzz.py` |
| `aiir/_schema.py` | `tests/test_schema.py` | `schemas/test_vectors.json`, `tests/test_public_surface.py` |
| `aiir/_verify.py` | `tests/test_verify.py` | `tests/test_hardening.py`, `tests/test_redteam.py`, mutation testing |
| `aiir/_canonical_cbor.py`, `aiir/_verify_cbor.py` | `tests/test_canonical_cbor.py`, `tests/test_cbor_conformance.py` | `schemas/cbor_test_vectors.json`, mutation testing |
| `aiir/_detect.py` | `tests/test_detect.py` | `tests/test_fuzz.py`, `schemas/unicode_evasion_vectors.json` |
| `aiir/cli.py` | `tests/test_cli_integration.py` | `tests/test_e2e_ux.py`, `tests/test_receipt.py` |
| `aiir/mcp_server.py` | `tests/test_mcp.py`, `tests/test_mcp_protocol.py` | `docs/agent-receipt-contract.md` |
| `aiir/_policy.py` | `tests/test_policy.py` | `tests/test_ledger_policy_signing_coverage.py` |
| `aiir/_github.py`, `aiir/_gitlab.py`, templates, examples | `tests/test_github.py`, `tests/test_gitlab.py`, `tests/test_examples.py` | YAML lint through full local CI |
| `.github/workflows/`, `action.yml` | `tests/test_action_shell.py`, `tests/test_ci_sigstore_gates.py` | SHA pin review, actionlint in CI |
| `scripts/` | `tests/test_scripts.py` | SPDX header check, full local CI |
| Release, publish, provenance evidence | `tests/test_emit_release_attest.py`, `tests/test_verify_release.py` | `tests/test_enforce_pypi_provenance.py`, `tests/test_pep740_preflight_rehearsal.py` |

## Repository invariants

These rules are blocking for AIIR, even if a change otherwise looks small:

- No new runtime dependencies. The package remains standard-library-only.
- Hash comparisons use `hmac.compare_digest()`.
- No real secrets, tokens, private hostnames, or internal project names.
- GitHub Actions `uses:` entries are pinned to full 40-character SHAs.
- Python files under `aiir/` include SPDX headers.
- Version changes pass `python scripts/sync-version.py --check`.

Receipt format, hashing, canonical JSON, CBOR, Sigstore, policy, and release
verification changes should run the full local CI profile before review. Changes
to `_verify.py`, `_canonical_cbor.py`, or `_verify_cbor.py` should also run the
mutation gate before merge unless they are documentation-only.

## PR testing notes

Every pull request should list what ran locally. Good examples:

```text
Tests:
- python -m pytest tests/test_verify.py -q
- scripts/ci-local.sh required
```

```text
Tests:
- Not run locally; documentation-only change.
```

For contributor ergonomics, focused tests are enough while a PR remains in
draft. Maintainers should run the required local CI gate before pushing a
branch that is ready to merge, and CI must pass before merge.
