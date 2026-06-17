# Release Health

**Last verified**: 2026-05-11
**Current release**: v1.6.0
**Release channel**: [@v1](https://github.com/invariant-systems-ai/aiir/releases/tag/v1) always points to the latest stable v1.x.x

| Status | Badge |
|---|---|
| CI (all platforms) | [![CI](https://github.com/invariant-systems-ai/aiir/actions/workflows/ci.yml/badge.svg)](https://github.com/invariant-systems-ai/aiir/actions/workflows/ci.yml) |
| Release smoke test | [![Release Smoke](https://github.com/invariant-systems-ai/aiir/actions/workflows/release-smoke.yml/badge.svg)](https://github.com/invariant-systems-ai/aiir/actions/workflows/release-smoke.yml) |
| Security | [![Security](https://github.com/invariant-systems-ai/aiir/actions/workflows/security.yml/badge.svg)](https://github.com/invariant-systems-ai/aiir/actions/workflows/security.yml) |
| OpenSSF Scorecard | [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/invariant-systems-ai/aiir/badge)](https://scorecard.dev/viewer/?uri=github.com/invariant-systems-ai/aiir) |

---

## Severity Definitions

| Severity | Definition | Response SLA | Public disclosure |
|---|---|---|---|
| **P0 — Critical** | Published release is broken, malicious, or exposes a security vulnerability affecting users | Fix or yanked within 24h; **RCA published within 48h** | Always |
| **P1 — High** | Core feature unavailable or produces incorrect results; workaround exists | Fix in next patch release | In release notes |
| **P2 — Medium** | Non-core feature degraded; or edge case incorrect behavior | Fix within 2 patch releases | In release notes |
| **P3 — Low** | Cosmetic or documentation issue | Best effort | In changelog |

---

## P0 Policy

Any P0 issue triggers the following mandatory process:

1. **T+0**: Issue acknowledged; workaround communicated in GitHub issue within 4h
2. **T+0–24h**: Fix released or affected version yanked from PyPI/Marketplace
3. **T+24–48h**: Root-cause analysis (RCA) published in the [RCA Archive](#rca-archive) below
4. **T+72h**: Post-mortem issue opened with prevention checklist

The RCA MUST include:

- Timeline of events (UTC)
- Root cause (technical and process)
- Impact assessment (who, how many, what data/operations affected)
- Immediate remediation taken
- Prevention: what changes prevent recurrence

---

## Smoke Test Coverage

After every release, the [release smoke workflow](../.github/workflows/release-smoke.yml) runs automatically:

| Check | What it tests |
|---|---|
| Install from PyPI | `pip install aiir==<version>` succeeds (no dep conflicts) |
| Version match | `aiir --version` matches the git tag |
| Receipt generation | `aiir --pretty` produces a valid receipt from a test commit |
| Ledger verify | `aiir --verify <ledger>` passes on a fresh ledger |
| CBOR round-trip | Receipt hashes match across JSON ↔ CBOR encoding |

Failure of any smoke check = automatic P0 alert (GitHub issue opened with alert label).

---

## Release Channels

| Channel | What | Update frequency |
|---|---|---|
| `@v1` (GitHub Action tag) | Latest stable v1.x.x | On every v1.x.x release |
| `receipt@1` (GitLab CI component) | Latest stable v1.x.x | On every v1.x.x release |
| `aiir` on PyPI | Latest stable | On every release |
| `ghcr.io/invariant-systems-ai/aiir` | Docker image, tagged by version | On every release |

Breaking changes (MAJOR version bump) will never be shipped to `@v1` or `receipt@1` — those tags are pinned to stable v1.x.x.

---

## Known Issues

No active release incidents are currently tracked. Routine CI and documentation maintenance does not affect the published v1.6.0 release.

Open a [GitHub issue](https://github.com/invariant-systems-ai/aiir/issues/new) to report a problem.

---

## RCA Archive

| Date | Severity | Version | Summary | Link |
|---|---|---|---|---|
| *(none)* | | | | |

---

## Release History (last 5)

| Version | Date | Key changes |
|---|---|---|
| v1.6.0 | 2026-06-04 | GitLab AI provenance evidence pack: CI template and guide producing a schema-validated declared-metadata evidence artifact |
| v1.5.1 | 2026-04-28 | Operator quick-reference docs and attestation coverage formatting cleanup |
| v1.5.0 | 2026-04-27 | Companion tool-context metadata and clearer separation between explicit AI attestation and companion IDE context |
| v1.4.0 | 2026-04-26 | Agent-receipt profile draft, offline transparency verification, pulse suggestion automation, and public-surface tightening |
| v1.3.0 | 2026-03-31 | Inference receipt verification, inference-bound evidence tier, release provenance policy enforcement, and refreshed extension/operator surfaces |

Full history: [CHANGELOG.md](../CHANGELOG.md)

---

For security vulnerabilities, see [SECURITY.md](../SECURITY.md). Do not open public issues for security bugs.
