# Governance & Adoption Action Plan

> Concrete June/July 2026 operating plan to move Governance (2.6 -> 3.5+)
> and Adoption (2.1 -> 3.0+) toward the standards-readiness green target.
>
> **Owner**: Noah / Invariant Systems
> **Created**: 2026-03-11
> **Rebaseline**: 2026-06-04
> **Target**: July 2026 public standards posture

---

## Current posture

| Lane | Current score | Green threshold | Blocking gap |
|---|---:|---:|---|
| Governance | 2.6 | 3.5 | IETF Datatracker submission, external review, and neutral-home path are still pending |
| Adoption | 2.1 | 3.5 | Internal dogfood proof exists; no external pilots are recorded |

The April/May work produced real artifacts: IETF draft renders, governance docs,
dogfood case study, blog drafts, SDK docs, and an implementers registry. The
remaining work is mostly external-state work: submissions, review asks, pilots,
and publication.

---

## June governance lane

### G1: Submit IETF Individual Draft

**Goal**: Submit `draft-invariantsystems-aiir-receipt-00` through Datatracker.

**Status**: artifacts rendered 2026-04-28; manual upload still pending.

Artifacts staged under `docs/ietf/`:

- `draft-invariantsystems-aiir-receipt-00.md`
- `draft-invariantsystems-aiir-receipt-00.xml`
- `draft-invariantsystems-aiir-receipt-00.txt`
- `draft-invariantsystems-aiir-receipt-00.html`

**Next steps**:

1. Re-read the rendered `.txt` and `.html` for stale version or date claims.
2. Submit via Datatracker as an Individual Draft.
3. Add the Datatracker URL to `SPEC.md`, `SPEC_GOVERNANCE.md`, and `docs/standards-readiness.md`.
4. Open a follow-up issue for any IETF formatting comments.

**Score impact**: Governance 2.6 -> about 3.0.

### G2: External review asks

**Goal**: Get at least two public review threads from adjacent provenance,
supply-chain, or scientific-computing communities.

**Target paths**:

| Target | Why | First artifact |
|---|---|---|
| OpenSSF / SLSA | Supply-chain provenance alignment | Short review issue asking about declared AI provenance fit |
| in-toto / Sigstore | Attestation and signing expertise | Focused issue on receipt signing and transparency evidence |
| Scientific reproducibility community | Research-evidence and inference receipts | Feedback request around reproducible AI-assisted artifacts |
| Marco Thiel / Wolfram workflow | Honest AI-assisted pedagogy and notebooks | Issue-first provenance note, no paper attachment initially |

**Next steps**:

1. Prepare one neutral "call for review" document.
2. Open or send two targeted review asks.
3. Record public threads in `docs/standards-readiness.md`.
4. Invite substantive reviewers to be external editors or advisors.

**Score impact**: each substantive external review can move Governance by
about +0.2 to +0.4, depending on depth.

---

## July governance lane

### G3: Neutral-home decision

**Goal**: Decide whether the next neutral-home move is CNCF Sandbox, IETF-only,
or a lighter advisory group.

**Prerequisite**: at least two external organizations or independent reviewers
express support or contribute review.

**Decision options**:

| Option | When it fits | Tradeoff |
|---|---|---|
| IETF-only for now | Datatracker draft receives useful review | Low process overhead, weaker adoption optics |
| CNCF Sandbox | Two or more orgs want implementation/adoption | Strong neutral-home signal, higher process load |
| Advisory group | Reviewers engage but adoption is still early | Practical near-term governance, less formal credibility |

**Next steps**:

1. Summarize June external review outcomes.
2. Pick one neutral-home path.
3. Open a public issue explaining the decision and next milestone.

**Score impact**: Governance 3.0 -> 3.5+ if the path is public and multi-party.

---

## June adoption lane

### A1: Keep dogfood proof fresh

**Status**: internal dogfood case study completed 2026-04-26.

**Remaining cleanup**:

1. Keep `.aiir/receipts.jsonl` locally verifiable.
2. Keep README, launch drafts, and website metrics aligned to the canonical
   scorecard values.
3. Treat broken receipt verification as public-surface debt, not just a test bug.

**Score impact**: preserves Adoption 2.1; does not materially raise it alone.

### A2: Public pilot outreach

**Goal**: Help three public OSS projects generate optional AIIR receipts.

**Selection criteria**:

- Uses AI-assisted development or has visible AI co-authorship.
- Has a public CI pipeline where an optional/manual workflow can be reviewed.
- Maintainer is likely to value reproducibility, provenance, education, or trust.

**First-contact rule**:

Open an issue before a PR unless the maintainer already asked for implementation.
Frame AIIR as optional declared-provenance infrastructure, not as detection,
compliance pressure, or vendor insertion.

**Candidate tracking**:

| Candidate type | First ask |
|---|---|
| Educational AI/model-building repos | README note plus optional local receipts |
| Supply-chain/security repos | Review of format assumptions and signing posture |
| Scientific notebook/workflow repos | Provenance receipts for declared AI-assisted development |

**Score impact**: three public pilots can move Adoption 2.1 -> about 2.7.

### A3: Publish one long-form artifact

**Goal**: Publish one durable post or article after the website metrics are
current.

Drafts staged under `docs/drafts/`:

- `verifiable-ai-provenance-in-practice.md`
- `aiir-self-dogfood-post.md`

**Next steps**:

1. Decide whether the canonical publication route is `invariantsystems.io/blog/`
   or a static article page.
2. Update public metrics before publishing.
3. Publish one article and link it from README or docs.

**Score impact**: published artifact plus pilot outreach can move Adoption
toward 3.0.

---

## Operating rules

1. Weekly standards issues should have one active cycle only; superseded weekly
   issues should be closed automatically.
2. Every public metric must point to a canonical source and a "Last verified" date.
3. Outreach should reveal only the public product surface: declared involvement,
   deterministic receipts, local verification, optional CI artifacts.
4. Do not claim hidden AI use can be detected or proven.
5. Do not attach deeper roadmap, scoring, enrichment, or enterprise strategy to
   first-contact OSS issues.

---

## Recommended next public sequence

1. Patch and deploy stale website metrics.
2. Submit the IETF draft through Datatracker.
3. Publish the neutral call-for-review note.
4. Open two targeted review issues.
5. Start one optional provenance issue with an educational/scientific repo.
6. Re-score Governance and Adoption in the next weekly standards cycle.
