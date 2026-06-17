# AIIR Public OSS Surface Audit

Date: 2026-06-04
Audited repo ref: `origin/main` at `90999d5994296db7786e5120d0c6550b12ae22b6`
Audit branch: `audit/public-surface-2026-06-04`
Branch-cleanup follow-up: `chore/close-branch-audit-followup-2026-06-04`

This audit covers the public AIIR OSS surface: GitHub repository state, default
README/quickstart paths, release metadata, docs, specs, schemas, examples,
automation, branch/issue hygiene, the checked-in `.aiir` snapshot, and the live
website funnel at <https://invariantsystems.io/>.

## Summary

AIIR's public repo surface is strong technically: stable commit receipts,
schema/test-vector coverage, release evidence, a public standards-readiness
scorecard, GitHub/GitLab/SDK/MCP integration surfaces, and a live dogfood
receipts branch. The main weakness is operational drift around public claims and
idea loops. Weekly standards-readiness issues had accumulated, the governance
and adoption plan needed a June/July rebaseline, the live website was stale
versus the repo before the website remediation PR and verified deploy, and
several public draft/launch artifacts need an owner or archive path.

## Fixes Landed In This Audit Branch

| Surface | Finding | Change |
|---|---|---|
| CLI quickstart | `aiir --verify .aiir/receipts.jsonl` failed because `--verify` treated JSONL as one JSON document. | Routed `.jsonl` paths through the existing ledger verifier and added passing/failing CLI tests. |
| Checked-in `.aiir` snapshot | `.aiir/receipts.jsonl` had 258 lines, but two were invalid test-looking entries. | Removed the two invalid entries, rebuilt `.aiir/index.json`, and added a public-surface test that the snapshot verifies. |
| Specification trust language | `SPEC.md` trust-tier table described signed/enveloped receipts as `tamper-proof`. | Reworded Tier 2/3 integrity to tamper-evident signing/envelope language. |
| Threat/launch claims | One launch draft and one threat-model recommendation still implied a tamper-proof upgrade. | Reworded to signed non-repudiation / transparency-log evidence. |
| Launch proof counts | `docs/launch/show-hn-draft.md` had stale `2,299` tests and `44` checks. | Updated to `2,499` tests and `145` public checks. |
| Citation metadata | `CITATION.cff` used version `1.5.1` with `date-released: 2026-03-31`; release-health says `2026-04-28`. | Updated citation date and added a release/citation consistency test. |
| Weekly standards loop | Weekly standards issues accumulated when prior cycles were not manually closed. | Added superseded-issue closeout to `.github/workflows/standards-readiness.yml` and guarded it with a public-surface test. |
| Governance/adoption plan | The plan still referenced April/May targets after the W23 catch-up. | Rebaselined to a June/July 2026 operating plan and updated the scorecard roadmap. |

## Priority Findings

| Priority | Finding | Evidence | Recommended action |
|---|---|---|---|
| P0 | Live website metrics were stale against the repo at audit time; remediation is merged and deployed. | Website previously showed `2214` tests, `41` checks, and `Last reviewed: 2026-03-31`; repo scorecard says `2,499`, `145`, and `2026-06-04`. `invariant-systems-ai/invariantsystems.io#27` patched the website source, and the published `stats.json` plus homepage now show those values. | Keep website metrics tied to canonical repo sources or add a published-site freshness check. |
| P1 | Weekly standards loop created reminders but did not enforce closeout. | `.github/workflows/standards-readiness.yml` now closes older open `standards-readiness` issues as superseded. | Verify the next scheduled Monday run and close any remaining historical standards issues by hand if needed. |
| P1 | Governance/adoption plan was past-due. | `docs/governance-adoption-plan.md` is now rebaselined to June/July 2026 with Datatracker, review, pilot, and publication rows. | Execute the plan; do not let it become a parked strategy doc again. |
| P1 | Public branch cleanup is complete for the 2026-06-04 audit. | Public branches after cleanup are `main` and `receipts`. The stale `codex/report-shared-webview-command-bridge-bug`, `fix/assisted-by-trailer`, and `feat/automation-secrets-sync` branches were pruned on 2026-06-04 after confirming their useful changes were already present on `main` or no longer needed. | Keep the public branch list this small; use short-lived PR branches for future cleanup work. |
| P1 | GitLab mirror drifted from GitHub after the public branch cleanup. | GitLab `main` was at `eaea6a7` while GitHub `main` was at `4d91a6d`; GitLab also had `feat/quantum-workload-provenance` and `recovery/vscode-history-20260528-aiir` heads and no `receipts` branch. Review showed the inference, sigstore, and quantum changes already landed on GitHub in newer form; the recovery branch is backlog/draft material. | Hardened `.github/workflows/sync.yml` to mirror only `main` and `receipts`, prune non-canonical GitLab heads, and verify branch SHA parity. GitLab `main` is protected with force-push disabled, so this workflow fast-forwards `main` but requires a one-time owner-side reset if `main` has already diverged. |
| P1 | Website is not in this local workspace, so repo tests cannot currently enforce live website freshness. | Public-surface tests skip sibling website checks when absent. | Ensure the website checkout/deploy pipeline is available to maintenance agents or add a scheduled public-site snapshot check. |
| P2 | Issue #136 was mostly done. | `CONTRIBUTING.md` already documents Windows symlink privilege / `WinError 1314`; #136 was closed as completed during cleanup. | Track a separate skip-strategy issue only if this recurs. |
| P2 | Draft surfaces are valuable but easy to confuse with stable commit receipts. | Agent and research receipt docs are public v0.1 drafts; commit receipts are stable. | Keep README wording explicit: stable commit receipts first, draft profiles second. |

## Row-By-Row Surface Audit

| Row | Surface | Current state | Risk / gap | Action |
|---:|---|---|---|---|
| 1 | GitHub repo visibility | Public repo, default branch `main`, squash-only merges enabled, auto-merge enabled. | Good public shape. | Keep. |
| 2 | Branch protection/ruleset | `.github/rulesets/main-production-gate.json` requires PRs, linear history, non-deletion, and status checks: `contribution-assessment`, `ci-ok`, `quality-ok`, `security-ok`. | Required review count is `0`; fine for solo velocity, weak for standards-governance optics. | Keep now; revisit when an external maintainer/editor exists. |
| 3 | Open PRs | None open after the W23 cleanup merge. | Clean. | Keep. |
| 4 | Open issues | Four open issues after closing #136: #122, #142, #101, #100. | Issue tracker is small but governance/adoption issues are still broad. | Keep #100/#101/#122 as external-facing; schedule #142. |
| 5 | Weekly standards issues | Prior weekly issues drifted open until cleanup; workflow now closes superseded weekly issues. | Needs one live scheduled run to prove the closeout path. | Verify the next Monday run. |
| 6 | Remote branches | GitHub public remote branches are now `main` and `receipts`. `codex/report-shared-webview-command-bridge-bug` had zero net diff from `main`; `fix/assisted-by-trailer` and `feat/automation-secrets-sync` were stale duplicates whose useful changes already existed on `main`. All three were deleted on 2026-06-04. | Branch clutter is resolved for GitHub; GitLab mirror drift is handled separately below. | Keep `receipts`; delete stale PR branches after merge or explicit archival. |
| 7 | Release tags | `v1` and `v1.5.1` point at `5393344`; `origin/main` is newer at `90999d5`. | Normal post-release mainline state. | Keep; release-health should remain current. |
| 8 | Python package metadata | `pyproject.toml`, `aiir/__init__.py`, `docs/api.md`, README examples all align on `1.5.1`. | Good. | Keep. |
| 9 | Citation metadata | Fixed in this branch to `1.5.1` / `2026-04-28`. | Previously stale. | Guarded by test. |
| 10 | JS SDK metadata | `sdks/js/package.json` at `1.5.1`; zero-dependency verifier positioning. | Good. | Keep. |
| 11 | Rust SDK metadata | `sdks/rust/Cargo.toml` at `0.1.0`. | Version skew is probably intentional but could confuse users. | Document independent SDK cadence in `docs/sdks.md` if not already clear enough. |
| 12 | VS Code extension metadata | `extensions/vscode/package.json` at `0.5.2`, independent from core. | Same cadence clarity issue. | Add one sentence in extension docs/release notes if needed. |
| 13 | GitHub Action | `action.yml` is composite, pinned setup-python, Sigstore optional/default signing. | Good public integration. | Keep; continue action-health freshness audits. |
| 14 | GitLab integration | `.gitlab-ci.yml`, templates, docs, and GitLab summary/MR support exist. GitLab mirror drift was found during the 2026-06-04 cleanup and the sync workflow now mirrors only canonical `main`/`receipts` heads, prunes stale GitLab branches, and verifies branch parity. | Good integration surface, but mirror health depends on the `GITLAB_TOKEN` secret, scheduled Sync runs, and a protected-branch policy that allows an owner-side reset when drift is already non-fast-forward. | Rotate/fix `GITLAB_TOKEN`, reset GitLab `main` once, and keep automation-secrets docs current. |
| 15 | MCP manifest | `mcp-manifest.json` advertises seven tools and multiple clients. | Strong surface; tool identity claims must stay careful. | Keep; avoid implying companion context means AI authorship. |
| 16 | README landing | Strong task-first onboarding and explicit limitations. | Long and dense; risk is cognitive overload, not inaccuracy. | Keep top path terse; move deep strategy to docs. |
| 17 | README quickstart | Now truthful after `.jsonl` verify fix. | Previously broken for default ledger. | Guard with tests. |
| 18 | README proof points | Repo claims `2,499` tests, `145` checks, 100% coverage. | Repo docs and published website metrics are aligned after `invariant-systems-ai/invariantsystems.io#27`. | Keep website/source freshness in the public audit loop. |
| 19 | `.aiir/README.md` | Clearly distinguishes checked-in snapshot from live `receipts` branch. | Good. | Keep. |
| 20 | `.aiir/receipts.jsonl` | Now 256/256 valid receipts. | Snapshot was previously broken by two invalid entries. | Guarded by public-surface test. |
| 21 | `receipts` branch | Current live dogfood branch has receipts for `90999d5`. | Good proof surface. | Keep branch protected from accidental deletion. |
| 22 | `SPEC.md` | Normative spec with CDDL, verification, tiers, security surfaces. | Trust table needed wording fix; done. | Keep current-claim tests. |
| 23 | `SPEC_GOVERNANCE.md` | Public governance, change control, extension policy. | Still vendor-led; no external body yet. | Tie next steps to Datatracker/external editor issues. |
| 24 | IETF draft artifacts | `docs/ietf/draft-invariantsystems-aiir-receipt-00.{md,xml,txt,html}` exist. | Rendered artifacts are not the same as Datatracker submission. | Submit or mark as staged-only with target date. |
| 25 | Standards-readiness scorecard | W23 updated with 79.1 composite, 3/5 green categories, 0 P0s; roadmap now points to June/July work. | Governance/adoption red; weekly loop needs next-run verification. | Keep weekly cadence and closeout automation. |
| 26 | Canonical metric sources | Scorecard lists sources and last-verified dates; website source now carries the W23 values. | Website source can still drift between audits if metrics remain hand-copied. | Extend canonical metric policy to website deploys or add a scheduled published-site freshness check. |
| 27 | Governance/adoption plan | Rebaselined to June/July 2026. | Still execution-heavy and external-state dependent. | Convert high-priority rows into issues after website metrics are fixed. |
| 28 | Launch checklist | Many unchecked launch/posting tasks remain; live website metrics item is now explicit. | Good ideas are parked but not owned. | Convert live launch tasks into issues or archive the launch folder as historical. |
| 29 | Blog/draft docs | Drafts for dogfood, provenance, Reddit, Show HN, Agent Trace issue exist. | Drafts age quickly and can retain stale metrics. | Add "last reviewed" headers or move stale drafts to archive. |
| 30 | Agent-receipt profile | Public v0.1 draft with schema and vectors; issue #122 open for feedback. | Good strategic surface; not stable. | Keep clearly labeled as draft; solicit feedback after core public surface is fresh. |
| 31 | Research-evidence profile | Public v0.1 verify-only profile and NISQ case study. | Niche and possibly distracting from core AIIR unless framed as boundary example. | Keep separate from main onboarding. |
| 32 | Inference receipt verification | Verify-only code and API docs exist; README has brief examples. | No standalone profile doc/paper-linked narrative comparable to agent/research receipts. | If using the AI inference paper strategically, add a narrow `docs/inference-receipts.md` before outreach. |
| 33 | Case studies | Internal dogfood and NISQ research evidence case studies exist. | Adoption still lacks external pilots. | Keep internal case study; pursue 2-3 external pilot rows. |
| 34 | Implementers registry | Lists Python reference, JS verifier, Rust verifier, and only Invariant Systems as user. | Honest, but adoption score remains low. | Do not inflate; add real pilots only. |
| 35 | Security docs | `SECURITY.md`, `.github/SECURITY.md`, `THREAT_MODEL.md`, CodeQL, Scorecard, fuzzing. | Strong; threat model wording fixed. | Keep current. |
| 36 | Release health | `docs/release-health.md` tracks v1.5.1 and release channels. | Last verified 2026-05-11; not W23. | Refresh on next release or monthly public audit. |
| 37 | Automation secrets | Public metadata, docs, tests, and workflow references exist on `main`; no values are in the repo. | Branch history looked half-merged before cleanup. | Done for this audit cycle; keep future automation-secrets work on short-lived PR branches. |
| 38 | Action health workflow | Weekly smoke/freshness audit creates issues. | Useful, but can create stale advisory issues if not closed. | Pair issue-opening workflows with closeout/supersede rules. |
| 39 | Pulse suggestions | Workflow can scaffold PRs from `[Pulse]` issues. | Good intake pattern; no open pulse items now. | Keep. |
| 40 | Dependabot/auto-merge | Dependabot + auto-merge workflows active; cleanup merged current action bumps. | Good if branch protection stays strict. | Keep. |
| 41 | Conformance schemas/vectors | CDDL, JSON schemas, conformance manifest, stable vectors, draft profile vectors. | Strong. | Keep external implementer ask active. |
| 42 | Examples/templates | GitHub Actions, GitLab, Azure, Bitbucket, CircleCI, Jenkins, Docker, pre-commit examples. | Broad surface increases drift risk. | Add a periodic docs-example smoke if not already covered. |
| 43 | Public website | Website source and published site now show `2,499` tests, `145` checks, and `Last reviewed: 2026-06-04` after `invariant-systems-ai/invariantsystems.io#27`. | Still needs a regression check so freshness does not drift again. | Consider scheduled fetch/snapshot regression. |
| 44 | OpenSSF / ecosystem feedback | Issue #100 remains open and relevant. | Good strategic doorway, but broad. | After website/standards loop cleanup, comment with specific asks or close if superseded. |
| 45 | First policy example | Issue #101 remains open. | Important adoption bridge; still unowned. | Treat as next high-ROI docs/example task. |
| 46 | CodeQL cyclic import | Issue #142 tracks maintainability cleanup. | Low severity but public code scanning note. | Schedule after current public-surface cleanup. |

## GitLab Mirror Reconciliation

Live GitLab review on 2026-06-04 found `main` diverged from GitHub by 20
GitLab-only commits and 24 GitHub-only commits. Most GitLab-only commits were
old merge/sync commits. The non-merge work was reviewed before pruning:

- `9780e16` (`Add inference verification and Copilot surfaces`) is already on
  GitHub as PR #77 (`4c4b116`) with later follow-up changes.
- `0e02d95` (`docs: fix version drift and harden action sigstore install`) is
  already present on current GitHub in 1.5.x form.
- `7545186` (`docs(readme): mark AIIR as research surface under 90-day proof
  gate`) is outdated for the current public README posture and should not be
  ported.
- `gitlab/feat/quantum-workload-provenance` is superseded by GitHub PR #140
  and the later research-evidence work in PR #143.
- `gitlab/recovery/vscode-history-20260528-aiir` contains broad universal and
  portable-provenance draft contracts from editor history. Treat it as backlog
  reference if those profiles are revived, not as stable public surface.

Follow-up verification after PR #164 showed GitLab `receipts` could be created
and the stale GitLab-only branches could be deleted with maintainer credentials,
but GitLab `main` is protected with `allow_force_push: false` and was already
non-fast-forward from GitHub. The Sync workflow therefore treats protected
`main` as a fast-forward-only mirror branch. One owner-side GitLab reset or a
temporary protected-branch force-push window is required to make `main` exact
again; after that, routine Sync pushes should stay fast-forward.

## Recommended Next Sequence

1. Rotate/fix the GitLab mirror token, reset GitLab `main` once to GitHub
   `main`, and confirm GitLab exposes only `main` and `receipts` at the same
   SHAs as GitHub.
2. Verify the next standards-readiness workflow run closes superseded issues.
3. Pick one adoption bridge: either #101 policy example or a focused
   `docs/inference-receipts.md` tied to the AI inference paper.
4. Only after the surface is fresh, open the Marco Thiel conversation as an
   issue-first outreach, with no partnership language and no paper attached on
   first contact.

## Notes On Marco / Inference Paper Strategy

For first contact with Marco Thiel, keep the discussion about his repo and
optional declared-AI provenance receipts. Do not attach the AI inference paper
in the first issue. The paper can become relevant later if the conversation
turns toward AIIR's inference-bound evidence tier or Wolfram notebook
workflows. First contact should stay small: README note, optional local
receipts, no hosted service, no hidden-AI detection claim.
