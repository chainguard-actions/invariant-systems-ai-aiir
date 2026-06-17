# Launch Sequence — Pre-Launch Checklist

> **Strategy**: Technical communities first → GitHub distribution → selective
> Reddit/Lobsters → Product Hunt → buyer outreach.
> **Rule**: No firehose. Earn proof points before seeking broad attention.

---

## Pre-launch gates (fix before inviting attention)

- [x] **End-to-end demo above the fold** — Generate → Verify → CI in one visual
- [x] **Fix mailto early-access flow** — pricing.html now POSTs to workers.dev
- [x] **GitLab copy-paste fix** — index.html Catalog snippet uses `@1` (major pin)
- [ ] **Patch live website metrics** — invariantsystems.io must match `docs/standards-readiness.md` canonical values: 2,499 tests, 145 public checks, last reviewed 2026-06-04
- [x] **Proof Points section** — README now has 9-row verifiable evidence table
- [x] **Marketplace badge** — added to README
- [x] **Repo description** — updated to mention verification + attestation
- [x] **Repo topics** — added slsa, verification, attestation, in-toto, supply-chain-security
- [x] **Release notes template** — .github/release.yml with structured categories
- [x] **Pin demo GIF/SVG** — docs/demo.svg refreshed to the current install and verify flow
- [x] **Verify browser verifier** — invariantsystems.io/verify accepts a real repo receipt and returns a valid integrity result
- [ ] **Create sample repo** — tiny repo showing receipt generation + browser verification + CI artifact in one pass

---

## Channel 1: Show HN

- [ ] Review [docs/launch/show-hn-draft.md](show-hn-draft.md)
- [ ] Post Tuesday–Thursday, 8–10am ET
- [ ] Reply to every comment in first 2 hours
- [ ] Be transparent about limitations and early-stage repo maturity
- [ ] Link to THREAT_MODEL.md when limitations are raised

## Channel 1a: Blog / Long-form

- [x] Draft broad launch post: [Verifiable AI Provenance in Practice](../drafts/verifiable-ai-provenance-in-practice.md)
- [x] Draft dogfood post: [AIIR Receipts AIIR](../drafts/aiir-self-dogfood-post.md)
- [ ] Decide publication route on invariantsystems.io (`/blog/` or static article page)
- [ ] Publish only after the internal closure gate passes

## Channel 2: GitHub distribution

- [x] Ensure README renders perfectly on github.com (images, badges, links)
- [x] Verify Marketplace listing shows latest README
- [ ] Consider creating `invariant-systems-ai/aiir-example` sample repo
- [ ] Star the repo from personal account (not org)

## Channel 3: Reddit / Lobsters (selective, personal)

- [ ] Only post as founder with disclosed affiliation
- [ ] Target: r/netsec, r/devops, r/programming, r/ExperiencedDevs
- [ ] Lobsters: submit with `show` tag, AI + security tags
- [ ] Keep self-promotion to <25% of total activity on each platform
- [ ] Never ask for upvotes

## Channel 4: Product Hunt (later)

- [ ] Wait for HN/GitHub proof points first
- [ ] Collect screenshots, early-user quotes
- [ ] Schedule as a separate beat after initial traction

## Channel 5: Buyer outreach (parallel)

- [ ] Create one crisp artifact: signed receipt from sample repo + verifier demo
- [ ] LinkedIn/X posts from founder account
- [ ] Direct outreach to design partners (security teams, compliance officers)
- [ ] Target: SOC 2 auditors, EU AI Act compliance leads, insurance underwriters
