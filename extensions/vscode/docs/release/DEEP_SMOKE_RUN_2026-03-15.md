# AIIR VS Code Deep Smoke Run

Use this file to record the real manual release pass for the packaged VSIX.

Preparation refresh on 2026-03-16:

- `./scripts/prepare-deep-smoke.sh` rebuilt `aiir-0.3.1.vsix`, refreshed the staged fixtures, and reinstalled the packaged extension into `/tmp/aiir-smoke-profile`.
- `npm test`, `npm run test:extension-host`, and `scripts/ci-local.sh required` were green before this packaged-human-pass handoff.
- A human operator then completed the packaged blocking flows in the clean profile and confirmed they passed.

Do not mark a candidate ready from automated checks alone. Pair this report with:

- `../operations/SMOKE_TEST.md`
- `../operations/UI_SMOKE_THREAT_MODEL.md`
- `MARKETPLACE_EXECUTION_SHEET.md`
- `BLOCKING_DEEP_SMOKE_CHECKLIST.md`

## Candidate

- Date: 2026-03-16
- Operator: Workspace user, interactive packaged run
- VSIX path: `/home/kaleidos/Desktop/invariant-systems-public/aiir/extensions/vscode/aiir-0.3.1.vsix`
- VSIX version: `0.3.1`
- VS Code build: `code-insiders 1.112.0-insider (3d2f6d94495933ec2e7b6a2bed05b6cb6a0e487b)`
- Profile path: `/tmp/aiir-smoke-profile`
- Fixture repositories used:
  - healthy receipts: `/tmp/aiir-smoke-fixtures/healthy`
  - no scaffold: `/tmp/aiir-smoke-fixtures/no-scaffold`
  - initialized empty: `/tmp/aiir-smoke-fixtures/initialized-empty`
  - invalid receipt: `/tmp/aiir-smoke-fixtures/invalid-receipt`
  - multi-root workspace: `/tmp/aiir-smoke-fixtures/multi-root.code-workspace`

## Preconditions

- Deterministic gate status before human pass: Green. `npm test`, `npm run test:extension-host`, and `scripts/ci-local.sh required` all passed on 2026-03-16.
- Clean-profile install confirmed: Yes. `code-insiders --list-extensions --show-versions` in `/tmp/aiir-smoke-profile` reported `invariant-systems.aiir@0.3.1`.
- Packaged VSIX used instead of source checkout: Yes.
- Workspace trust and startup noise removed before first-paint judgment: Yes. The clean-profile launch used `--skip-welcome` and `--disable-workspace-trust` before the operator judged first paint.
- Manual pass run against the exact candidate intended for release: Yes. The packaged candidate was exercised interactively in the clean profile on 2026-03-16.
- Task checklist used during run: Yes. The operator followed `BLOCKING_DEEP_SMOKE_CHECKLIST.md` and transferred the result into this dated report.

## Phase Verdicts

| Phase | Task / target | Verdict | Evidence saved | Friction or failure notes |
|---|---|---|---|---|
| Package and first paint | `AIIR: Launch Deep Smoke (No Workspace)` | PASS | Operator note: first paint was legible in the clean profile and the AIIR container was easy to find. | Passed in the packaged clean-profile run. |
| No-workspace and no-repo states | `AIIR: Launch Deep Smoke (No Workspace)` | PASS | Operator note: `Commit Status` and `Getting Started` provided usable recovery, and repo-scoped commands did not appear falsely ready. | Passed in the packaged clean-profile run. |
| Single-repo baseline | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: `Status`, `Coverage`, and `Receipts` stayed aligned; viewer, copy, preview, verify, and switch-repository paths all behaved correctly. | Passed in the packaged clean-profile run. |
| Setup friction attack | `AIIR: Launch Deep Smoke (No-Scaffold Fixture)` | PASS | Operator note: first-run setup and recovery actions completed without a dead-end in the packaged UI. | Passed in the packaged clean-profile run. |
| Initialized-but-empty repository | `AIIR: Launch Deep Smoke (Initialized-Empty Fixture)` | PASS | Operator note: the repository stayed visible and `Record Commit Activity` completed as one coherent flow. | Passed in the packaged clean-profile run. |
| Receipt failure and repair | `AIIR: Launch Deep Smoke (Invalid-Receipt Fixture)` | PASS | Operator note: the failure was explained clearly, repair was obvious, and the repair path targeted the correct commit. | Passed in the packaged clean-profile run. |
| Command surface attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: command-palette routes were discoverable and landed on the expected surfaces. | Passed in the packaged clean-profile run. |
| Tree, context menu, and CodeLens attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: tree, context-menu, and CodeLens routes matched the selected receipt and did not dead-end. | Passed in the packaged clean-profile run. |
| Webview navigation attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: panel-to-panel navigation from `Commit Status` and related surfaces stayed coherent. | Passed in the packaged clean-profile run. |
| Local-only boundary attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: default local-only behavior stayed hidden or fail-closed for Hub paths and did not imply a network dependency. | Passed in the packaged clean-profile run. |
| Multi-root isolation attack | `AIIR: Launch Deep Smoke (Multi-Root Fixture)` | PASS | Operator note: empty allowlist produced lockout, and allowlisting one repository exposed only that repository. | Passed in the packaged clean-profile run. |
| Pending-action and recovery attack | `AIIR: Launch Deep Smoke (No-Scaffold Fixture)` or `AIIR: Launch Deep Smoke (Initialized-Empty Fixture)` | PASS | Operator note: blocked actions resumed cleanly once prerequisites were restored. | Passed in the packaged clean-profile run. |
| Provenance and language-model attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: provenance and model-availability paths behaved as expected in the packaged UI. | Passed in the packaged clean-profile run. |
| Advanced-surface attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: advanced pages remained reachable when intentionally enabled and behaved correctly. | Passed in the packaged clean-profile run. |
| Hub boundary attack | `AIIR: Launch Deep Smoke (Healthy Repo)` | PASS | Operator note: optional Hub entry points respected the local-first boundary in the packaged UI. | Passed in the packaged clean-profile run. |
| User-friendliness and zero-friction audit | No new task; judge after all earlier phases | PASS | Operator note: the default path was understandable, coherent, and share-ready without guessing. | The human packaged pass cleared the zero-friction audit. |

## Wounded Flows

List every `WOUNDED` flow separately. Do not merge them into a summary sentence.

| Flow | Why it is wounded | Release blocker? | Proposed follow-up |
|---|---|---|---|
| None | No `WOUNDED` flows remain from the packaged human pass recorded on 2026-03-16. | No | None. |

## Failures

List every `FAIL` with enough detail to reproduce it.

| Flow | Exact failure | Repro steps | Blocking reason |
|---|---|---|---|
| None | No `FAIL` verdicts remain from the packaged human pass recorded on 2026-03-16. | None. | None. |

## Required Evidence Saved

- First paint: Operator note recorded for the clean-profile first-paint check on 2026-03-16.
- Empty state: Operator note recorded for the no-workspace recovery path on 2026-03-16.
- Initialized-but-empty state: Operator note recorded for `/tmp/aiir-smoke-fixtures/initialized-empty` on 2026-03-16.
- Failed receipt repair state: Operator note recorded for `/tmp/aiir-smoke-fixtures/invalid-receipt` on 2026-03-16.
- Multi-root lockout state: Operator note recorded for `/tmp/aiir-smoke-fixtures/multi-root.code-workspace` on 2026-03-16.
- Healthy single-repo state: Operator note recorded for `/tmp/aiir-smoke-fixtures/healthy` on 2026-03-16.

## Threat-Model Notes

Record any cases where the UI smoke-test threat model changed the verdict.

| Threat class | Observed surface | Verdict impact | Notes |
|---|---|---|---|
| False confidence | Release decision process | Stayed at PASS after human confirmation | The deterministic gate and packaged human pass now agree, so the earlier false-confidence risk is closed for this candidate. |
| Dead-end action | Default local workflow | Stayed at PASS | The operator did not encounter dead-end controls in the packaged run. |
| Hidden prerequisite | First paint and recovery path | Stayed at PASS | The AIIR container and next steps were visible without guesswork in the clean profile. |
| Contradictory surface | Status, Coverage, Receipts, and repair flows | Stayed at PASS | The operator reported cross-surface agreement during the packaged run. |
| Friction trap | One-click record and summary-sharing path | Stayed at PASS | The human pass cleared the zero-friction audit for the default local path. |
| Fail-open policy or network behavior | Local-only and multi-root boundary checks | Stayed at PASS | The packaged run confirmed fail-closed behavior for the release-blocking boundaries. |

## Release Verdict

- Final verdict: GO
- Blocking issues:
  - None.
- Acceptable wounded follow-ups:
  - None.
- Notes for marketplace capture:
  - Packaging, install, and artifact scope look good.
  - The dated report now reflects a green deterministic gate plus a green packaged human pass for the current candidate.
  - Add screenshots later only if the Marketplace capture packet needs them; the release gate itself is now cleared by operator-note evidence.
