# AIIR Standards-Readiness Scorecard

> **Update cadence**: weekly, every Monday.
> **Automation**: `.github/workflows/standards-readiness.yml` opens/updates the current weekly issue and closes superseded weekly issues.
> **Rationale**: AIIR is a vendor-led open specification on a public standards track.
> Transparent, weekly readiness scoring signals good-faith governance and tracks gap closure.
>
> **Public target**: 4 green categories (score ≥ 3.5/5) + no open P0 for 4 consecutive weeks → louder standards messaging.

---

## Weekly Operating Score: 2026-W23

Last updated: 2026-06-04

| Category | Score (0–5) | Status | Key gap |
|---|---|---|---|
| 🔴 Governance | 2.6 | ❌ red | IETF draft artifacts rendered; Datatracker upload and external steering still pending |
| ✅ Reliability | 4.6 | ✅ green | 2,499 tests collected and 100% coverage re-verified; external implementation needed for 5.0 |
| ✅ Interoperability | 4.1 | ✅ green | Commit-receipt SDKs and draft agent/research vector surfaces exist; external verifier still needed for 5.0 |
| 🔴 Adoption | 2.1 | ❌ red | Internal case study and outreach targets exist; no external pilots on record |
| ✅ Consistency | 4.1 | ✅ green | Canonical vectors, CDDL, and profile docs are current; external review needed for 5.0 |
| **Open P0s** | 0 | ✅ green | |

> **Green target**: ≥ 3.5/5 on all 5 categories for 4 consecutive weeks.
> Current: 3 green categories out of 5.

---

## Detailed 6-Dimension Score (underlying methodology)

Last updated: 2026-06-04 · Cycle: 2026-W23

| Dimension | Weight | Score (0–5) | Weighted | Gap |
|---|---|---|---|---|
| Technical completeness | 20 | 4.7 | 18.8 | External review for 5.0 |
| Reference implementation quality | 20 | 4.6 | 18.4 | External (non-Invariant) implementation for 5.0 |
| Specification clarity | 15 | 4.3 | 12.9 | External review |
| Reliability & ecosystem | 15 | 4.4 | 13.2 | Community plugins; external verifier |
| Governance neutrality | 20 | 2.6 | 10.4 | Datatracker submission; multi-stakeholder body; neutral IP home |
| Adoption maturity | 10 | 2.1 | 4.2 | External pilots and integrations in the wild |
| **Composite** | **100** | | **79.1** | |

*5-category → 6-dimension mapping*: Governance ≈ Governance neutrality. Reliability ≈ Technical completeness + Reference impl quality. Interoperability ≈ Reliability & ecosystem. Adoption ≈ Adoption maturity. Consistency ≈ Specification clarity + metric consistency.

Version of this doc: v1.1.2

---

## Scoring Rubric

Each dimension is scored 0–5 by the maintainer, reviewed weekly.
A score of 5 means "demonstrably complete — a standards body could adopt this today."

### Technical Completeness (weight 20)

| Score | Criteria |
|---|---|
| 0 | No spec; ad-hoc behavior |
| 1 | Informal draft; core concepts present |
| 2 | Spec covers happy path; edge cases underspecified |
| 3 | Spec covers error cases; versioning defined |
| 4 | Schema versioning, multi-encoder interop defined |
| 5 | CDDL/ABNF normative grammar; formal conformance suite |

**Current: 4.7** — Schema versioned in `schemas/`; deterministic CBOR + JSON dual encoding; `schemas/conformance-manifest.json` published (2026-03-11); normative CDDL grammar in `schemas/receipt.cddl` covering JSON + CBOR wire formats, refreshed for `aiir/commit_receipt.v2` DAG binding (2026-04-28); cross-language encoder interop test vectors published in `schemas/test-vectors/` (8 vectors covering key ordering, Unicode, booleans, numerics, boundary arrays — 2026-03-11); draft agent-receipt and research-evidence vector surfaces are now published under `schemas/test-vectors/`. Missing: external review.
*Last verified: 2026-06-04*

**Gap tasks:**

- [x] ~~Publish machine-readable conformance manifest~~ → `schemas/conformance-manifest.json` (2026-03-11)
- [x] ~~Write CDDL grammar for the receipt schema~~ → `schemas/receipt.cddl` (2026-03-11)
- [x] ~~Add encoder interop test vectors~~ → `schemas/test-vectors/encoder_interop_vectors.json` (2026-03-11)
- [x] ~~Publish test vector registry linked from `SPEC.md`~~ → `SPEC.md` §13 (2026-03-11)

---

### Reference Implementation Quality (weight 20)

| Score | Criteria |
|---|---|
| 0 | No test suite |
| 1 | Basic happy-path tests |
| 2 | Statement coverage ≥ 80% |
| 3 | Statement + branch coverage = 100% |
| 4 | Mutation tested; fuzzing in CI; adversarial inputs in suite |
| 5 | Formal adversarial corpus; independent implementation verified identical output |

**Current: 4.6** — 100% statement + branch coverage (2,499 tests collected, *last verified: 2026-06-04*); mutation testing; Atheris fuzzing in CI; structured adversarial rounds per release; post-release smoke tests automated; **formal adversarial test corpus published** in `tests/adversarial/` — 32 fixtures across 4 categories (injection, tampering, parsing, bypass) with auto-discovery pytest runner (2026-03-11). **JS verifier (`sdks/js/`) passes 8/8 encoder interop vectors and 8/8 full receipt verifications** (2026-03-11); **Rust CBOR verifier (`sdks/rust/`) passes round-trip vectors** (2026-03-11). Missing: external (non-Invariant Systems) implementation.
*Last verified: 2026-06-04*

**Gap tasks:**

- [x] ~~Post-release smoke test workflow~~ → `.github/workflows/release-smoke.yml` (2026-03-11)
- [x] ~~Publish adversarial test fixtures~~ → `tests/adversarial/` (32 fixtures, 4 categories — 2026-03-11)
- [x] ~~Document JS + Rust as second implementations~~ → `docs/implementers.md` (2026-03-11)
- [ ] Sponsor or recruit an independent (external org) implementation

---

### Specification Clarity (weight 15)

| Score | Criteria |
|---|---|
| 0 | No spec |
| 1 | README-level prose |
| 2 | `SPEC.md` exists with normative sections |
| 3 | Conformance profiles defined; `conformance.html` published |
| 4 | ABNF/CDDL normative grammar; unambiguous field semantics |
| 5 | Standards-body editorial style; external review completed |

**Current: 4.3** — `SPEC.md` with normative language; `conformance.html` live; receipt field semantics precisely defined; `SPEC_GOVERNANCE.md` published with change control, compat guarantees, extension registry, release cadence (2026-03-11); normative CDDL grammar in `schemas/receipt.cddl` referenced from `SPEC.md` section 1.3 and refreshed for v2 (2026-04-28); IETF draft artifacts rendered under `docs/ietf/` (2026-04-28); public docs now distinguish stable commit receipts from draft agent/research evidence profiles. Missing: external review.
*Last verified: 2026-06-04*

**Gap tasks:**

- [x] ~~Publish change control + compatibility policy~~ → `SPEC_GOVERNANCE.md` (2026-03-11)
- [x] ~~Add `schemas/receipt.cddl` (CDDL grammar; normative)~~ → (2026-03-11)
- [x] ~~Add "Conformance Testing" section to `SPEC.md` referencing test vectors~~ → SPEC.md §13 updated (2026-03-11)
- [ ] Solicit one external spec review (security researcher or standards professional)

---

### Reliability & Ecosystem (weight 15)

| Score | Criteria |
|---|---|
| 0 | No CI |
| 1 | Single-platform CI |
| 2 | Multi-platform CI; CI badge visible |
| 3 | Multi-platform + multi-Python; current main ref exposes 145 public check runs |
| 4 | Third-party verifier (non-AIIR) working; 2+ language SDKs |
| 5 | 3+ independent verifiers; community plugin ecosystem |

**Current: 4.4** — 145 public check runs on the latest `main` ref, with `ci-ok`, `quality-ok`, and `security-ok` enforced by branch protection (*last verified: 2026-06-04*); Python 3.9–3.13 × Ubuntu/Windows/macOS; GitHub + GitLab dual-publish; MCP tool; `docs/release-health.md` with P0 RCA policy and smoke test badge published; **JS verifier (`sdks/js/`) and Rust CBOR verifier (`sdks/rust/`) published — 2 language SDKs verified against test vectors** (2026-03-11). Missing: community plugins, external verifier.
*Last verified: 2026-06-04*

**Gap tasks:**

- [x] ~~Release health page + P0 RCA policy~~ → `docs/release-health.md` (2026-03-11)
- [x] ~~Post-release smoke tests~~ → `.github/workflows/release-smoke.yml` (2026-03-11)
- [x] ~~Write standalone receipt verifier in JS~~ → `sdks/js/aiir-verify.js` (Level 1 — 2026-03-11)
- [x] ~~Document the MCP interface in `mcp-manifest.json` as a first-class integration point~~ → `mcp-manifest.json`; GitLens Commit Composer workflow rule added (2026-04-28)
- [x] ~~Publish SDK guidance in `docs/sdks.md`~~ → `docs/sdks.md` (2026-05-02)

---

### Governance Neutrality (weight 20)

| Score | Criteria |
|---|---|
| 0 | Single vendor, no public governance |
| 1 | Apache 2.0 license; public repo |
| 2 | Public governance docs; contributor ladder |
| 3 | IP contributed to neutral home (e.g., CNCF sandbox) or formal RFC submitted |
| 4 | Active multi-org steering committee |
| 5 | Adopted by a standards body (ISO, IETF, W3C, NIST) |

**Current: 2.6** — Apache 2.0; public repo; public `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`; `SPEC_GOVERNANCE.md` published with SIG structure, change control, extension registry, IP policy, and standards-track roadmap (2026-03-11); `draft-invariantsystems-aiir-receipt-00` Markdown/XML/text/HTML artifacts rendered cleanly under `docs/ietf/` (2026-04-28). Missing: Datatracker submission, neutral IP home, multi-org steering.
*Last verified: 2026-04-28*

**Gap tasks (high-leverage, ordered by effort):**

- [x] ~~Publish `SPEC_GOVERNANCE.md` with SIG structure, RFC process, IP policy~~ (2026-03-11)
- [x] ~~Draft an IETF Individual Draft (`draft-invariantsystems-aiir-receipt-00.txt`)~~ → rendered artifacts in `docs/ietf/` (2026-04-28)
- [ ] Submit the IETF Individual Draft through Datatracker
- [ ] Open a CNCF Sandbox proposal (requires 2 additional organizations)
- [ ] Invite 2–3 external organizations to a working group
- [ ] Recruit external editor (≥ 1 org)

---

### Adoption Maturity (weight 10)

| Score | Criteria |
|---|---|
| 0 | No documented users |
| 1 | Creator uses it in their own repo |
| 2 | 2–5 public repos using AIIR receipts |
| 3 | Published case study; 10+ repos |
| 4 | Enterprise reference customer; recorded talk at a conference |
| 5 | Mentioned in a regulation, standard, or widely-cited OSS project |

**Current: 2.1** — AIIR uses AIIR (dogfooding, *last verified: 2026-06-04*); PyPI+GitHub Marketplace live; EU AI Act compliance positioning; `docs/implementers.md` registry published (invites external entries); public internal case study published at `docs/case-studies/aiir-self-dogfood.md`; outreach targets for AI-assisted OSS provenance have been identified. Missing: external adopters and third-party pilots on record.
*Last verified: 2026-06-04*

**Gap tasks (highest ROI for standards positioning):**

- [x] ~~Publish implementers/pilots registry~~ → `docs/implementers.md` (2026-03-11)
- [x] ~~Publish a first case study (even internal: "AIIR generates receipts for AIIR itself")~~ → `docs/case-studies/aiir-self-dogfood.md` (2026-04-26)
- [ ] Reach out to 3 OSS projects that commit AI-assisted code; offer to help them adopt
- [x] ~~Write a blog post / talk abstract: "Verifiable AI provenance in practice"~~ → draft staged in `docs/drafts/` (2026-04-28)
- [ ] Submit a talk to a supply-chain security conference (SOSS, OpenSSF Day, KubeCon)

---

## Canonical Metric Sources

> **Policy**: all comparison numbers in docs and on the website MUST trace to one of these sources.
> No hand-edited stat may appear without a "Last verified" date.

| Metric | Canonical source | Last verified |
|---|---|---|
| Test count | `pytest --collect-only -q \| tail -1` | 2026-06-04 (2,499 tests collected) |
| CI check count | GitHub check-runs API on the latest `main` commit | 2026-06-04 (145 public checks; 3 required merge gates) |
| Coverage | `pytest --cov=aiir --cov-fail-under=100` | 2026-06-04 (100%; 6,103 statements, 2,550 branches) |
| Runtime dependencies | `pip show aiir \| grep Requires` | 2026-03-11 (0) |
| Conformance vectors | `schemas/conformance-manifest.json` | 2026-03-31 (97 total across 8 stable commit-receipt vector files) |
| Release version | `aiir --version` / PyPI | 2026-06-04 (v1.6.0) |
| Governance score | This doc, Governance Neutrality section | 2026-06-04 (2.6/5, draft artifacts rendered; not submitted) |
| Adoption score | `docs/implementers.md` | 2026-06-04 (2.1/5) |

---

## Weekly Update History

| Cycle | Date | Score | Key change |
|---|---|---|---|
| 2026-W23 | 2026-06-04 | 79.1 | Catch-up scorecard refresh after W19-W22 drift; 2,499 tests collected; 100% coverage re-verified; 145 public check runs on latest `main`; draft agent/research evidence vector surfaces reflected |
| 2026-W22 | 2026-05-25 | 78.7 | Mainline proof-surface automation and dependency hygiene stayed active; standards issue was left open and is superseded by the W23 catch-up row |
| 2026-W21 | 2026-05-18 | 78.4 | Research evidence and automation proof-surface work landed; no governance/adoption score change recorded |
| 2026-W20 | 2026-05-11 | 77.6 | Public release docs aligned to v1.5.1 and SDK guidance matured; no external pilot recorded |
| 2026-W19 | 2026-05-04 | 76.8 | GitLens companion context and standards-surface cleanup held the W18 posture while follow-up issues accumulated |
| 2026-W18 | 2026-04-28 | 76.0 | IETF draft artifacts rendered cleanly under `docs/ietf/`; CDDL refreshed for `aiir/commit_receipt.v2`; GitLens Commit Composer MCP workflow rule documented; launch posts drafted |
| 2026-W17 | 2026-04-26 | 72.8 | Public dogfood case study published at `docs/case-studies/aiir-self-dogfood.md`; adoption score 1.7 → 2.0; README and implementers registry linked to the case study |
| 2026-W11 | 2026-03-11 | 72.2 | Adversarial corpus (32 fixtures, 4 categories) → Reliability 4.5; encoder interop vectors (8 vectors) → Consistency 4.0; JS verifier passes all vectors → Interop 3.8; Reliability+Ecosystem 4.2; composite +3.3 |
| 2026-W11 | 2026-03-11 | 68.9 | v1.1 scorecard → +1.4 CDDL: SPEC_GOVERNANCE.md, release-health.md, smoke tests, conformance-manifest.json, implementers.md, 5-category weekly model; normative CDDL grammar (schemas/receipt.cddl); SPEC.md section 1.3 + conformance-manifest updated |

---

## June/July Gap-Closure Roadmap

```text
Completed foundation work (Mar-Apr 2026)
  ✅ SPEC_GOVERNANCE.md published (change control, compat policy, extension registry)
  ✅ schemas/conformance-manifest.json published (machine-readable implementer registry)
  ✅ docs/release-health.md published (P0 policy, RCA template, smoke test badge)
  ✅ .github/workflows/release-smoke.yml (automated post-release smoke, P0 alert)
  ✅ docs/implementers.md published (third-party implementations + pilots registry)
  ✅ Weekly standards-readiness issue workflow, now with superseded-issue closeout
  ✅ CDDL grammar (schemas/receipt.cddl)
  ✅ Encoder interop test vectors (schemas/test-vectors/encoder_interop_vectors.json — 8 vectors)
  ✅ Publish adversarial fixture corpus (tests/adversarial/ — 32 fixtures, 4 categories)
  ✅ IETF draft artifacts rendered under docs/ietf/
  ✅ Standalone JavaScript receipt verifier (browser-native, Level 1)
  ✅ Internal dogfood case study published

June 2026: Governance submission + external review
  ✦ Submit draft-invariantsystems-aiir-receipt-00 through Datatracker
  ✦ Open two targeted external review threads
  ✦ Patch/deploy website metrics from canonical scorecard values
  ✦ Publish a neutral call-for-review note
  Target: Governance 2.6 -> about 3.0

June/July 2026: Adoption proof
  ✦ Start 3 optional OSS pilot conversations
  ✦ Record any public pilots in docs/implementers.md
  ✦ Publish 1 long-form article after website metrics are current
  ✦ Decide whether the neutral-home path is IETF-only, CNCF Sandbox, or advisory group
  Target: Adoption 2.1 -> about 3.0; Governance 3.0 -> 3.5+ if multi-party review lands

Green target: 4 categories ≥ 3.5/5 + 0 open P0s for 4 consecutive weeks
Current 2026-W23 posture: 3 categories green; governance and external adoption remain the blocking lanes.
```

---

## Methodology Notes

- Scores are maintainer-assessed; targets must be verifiable (link to artifact, PR, or commit).
- The weekly GitHub Action creates a tracking issue with a pre-filled update template.
- All historical scores are preserved in the "Weekly Update History" table above.
- This document lives at `docs/standards-readiness.md` and is linked from `invariantsystems.io`.

---

*AIIR is a vendor-led open specification on a transparent standards track.*
*We publish this scorecard weekly to signal good-faith governance and track gap closure in the open.*
