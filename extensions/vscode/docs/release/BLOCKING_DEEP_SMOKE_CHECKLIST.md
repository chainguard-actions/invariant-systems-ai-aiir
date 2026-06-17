# AIIR Blocking Deep Smoke Checklist

Use this page with `DETERMINISTIC_SMOKE_COVERAGE.md`. A blocking UX item is only closed when both the human smoke artifact and its mapped deterministic check are green.

Use this page when you only need the release-blocking human checks that still
stand between the current VSIX and a publish decision.

This is a reduced operator path derived from:

- `DEEP_SMOKE_RUN_2026-03-15.md`
- `../operations/SMOKE_TEST.md`

It is not a replacement for the full matrix. It is the shortest honest path to
clear the current `NO-GO` decision.

## Current Gate

The blocking gate for the current `aiir-0.3.1.vsix` candidate was cleared in
the dated report on 2026-03-16.

Current status:

1. `DEEP_SMOKE_RUN_2026-03-15.md` now records operator-pass verdicts for the packaged blocking flows.
2. `DETERMINISTIC_SMOKE_COVERAGE.md` remains green for the mapped automated checks.
3. Use this checklist again only for reruns, new capture sessions, or any candidate that changes after the recorded pass.

## Prep

1. Run `AIIR: Prepare Deep Smoke`.
2. Open `DEEP_SMOKE_RUN_2026-03-15.md` side-by-side.
3. Keep `../operations/UI_SMOKE_THREAT_MODEL.md` open for `WOUNDED` vs `FAIL` decisions.

## Source-Debug Mirror

Use these repo-root `Run and Debug` entries when you need to reproduce a smoke
finding against the current source build instead of the packaged VSIX:

- Blocking smoke start: `AIIR: Source Debug (Blocking Smoke Start)`
- Healthy baseline: `AIIR: Source Debug (Healthy Baseline)`
- Fixture sweep: `AIIR: Source Debug (Fixture Sweep)`

Use the per-scenario Extension Host launch when you need one exact target:

- No workspace: `AIIR: Extension Host (No Workspace)`
- Healthy repo: `AIIR: Extension Host (Healthy Repo)`
- No-scaffold: `AIIR: Extension Host (No-Scaffold Fixture)`
- Initialized-empty: `AIIR: Extension Host (Initialized-Empty Fixture)`
- Invalid receipt: `AIIR: Extension Host (Invalid-Receipt Fixture)`
- Multi-root: `AIIR: Extension Host (Multi-Root Fixture)`

## Blocking Path

### 1. First Paint And No-Workspace

- Task: `AIIR: Launch Deep Smoke (No Workspace)`
- Source-debug mirror: `AIIR: Source Debug (Blocking Smoke Start)` or `AIIR: Extension Host (No Workspace)`
- Must verify:
  - the AIIR container is visible and reachable
  - the default AIIR shell is `Status`, `Coverage`, and `Receipts`
  - first paint is legible after switching into AIIR
  - `AIIR: Commit Status` and `AIIR: Getting Started` provide a usable next step
  - repo-scoped commands do not appear falsely ready in a no-workspace window
- Save evidence:
  - first paint screenshot or exact operator note
  - no-workspace empty-state screenshot or exact operator note

### 2. Healthy Baseline

- Task: `AIIR: Launch Deep Smoke (Healthy Repo)`
- Source-debug mirror: `AIIR: Source Debug (Healthy Baseline)` or `AIIR: Extension Host (Healthy Repo)`
- Must verify:
  - `Status`, `Coverage`, and `Receipts` all render correctly
  - receipt tree items open the correct surfaces
  - receipt viewer actions work with the current labels: `Copy Receipt Summary`,
    `Preview Receipt Summary`, and `Open Receipt JSON`
  - the copied summary is usable as a PR handoff without cleanup
  - command palette routes to the correct surfaces
  - tree, context-menu, and CodeLens actions do not dead-end
  - default-shell panel navigation does not strand the user
  - repository switching is visible and keeps `Status`, `Coverage`, and `Receipts` aligned
- Save evidence:
  - healthy single-repo screenshot or exact operator note

### 3. Initialized-Empty Repository

- Task: `AIIR: Launch Deep Smoke (Initialized-Empty Fixture)`
- Source-debug mirror: `AIIR: Source Debug (Fixture Sweep)` or `AIIR: Extension Host (Initialized-Empty Fixture)`
- Must verify:
  - the repository stays visible in `Coverage` and `Receipts`
  - the next action is explicit and sensible
  - `Record Commit Activity` does not dead-end or bounce through stale setup copy
  - visible CTA behavior matches the actual state
- Save evidence:
  - initialized-but-empty screenshot or exact operator note

### 4. Failed Receipt Repair

- Task: `AIIR: Launch Deep Smoke (Invalid-Receipt Fixture)`
- Source-debug mirror: `AIIR: Source Debug (Fixture Sweep)` or `AIIR: Extension Host (Invalid-Receipt Fixture)`
- Must verify:
  - the failure is explained in human terms
  - the primary repair action is obvious
  - repair targets the exact commit referenced by the failed receipt
  - `Open Receipt JSON` and any visible secondary recovery actions work
- Save evidence:
  - failed receipt repair screenshot or exact operator note

### 5. Local-Only Boundary

- Reuse: `AIIR: Launch Deep Smoke (Healthy Repo)`
- Source-debug mirror: `AIIR: Source Debug (Healthy Baseline)` or `AIIR: Extension Host (Healthy Repo)`
- Must verify:
  - `aiir.strictLocalOnly` behaves as the default posture
  - hidden Hub commands stay hidden in the command palette
  - visible default-flow surfaces do not imply Hub is required
  - direct-route Hub entry points fail closed with readable copy

### 6. Multi-Root Isolation

- Task: `AIIR: Launch Deep Smoke (Multi-Root Fixture)`
- Source-debug mirror: `AIIR: Source Debug (Fixture Sweep)` or `AIIR: Extension Host (Multi-Root Fixture)`
- Must verify:
  - `aiir.enforceWorkspaceIsolation` plus an empty allowlist produces lockout
    instead of discovery
  - blocked repositories stay blocked through tree, file-open, and command routes
  - allowlisting only one repository exposes only that repository
- Save evidence:
  - multi-root lockout screenshot or exact operator note

### 7. Zero-Friction Audit

- No new task required.
- Judge this only after all checks above have real evidence.
- Minimum decision questions:
  - was the next action obvious?
  - did any visible control dead-end?
  - did any surfaces disagree about repository state?
  - would a new user understand what happened?
  - could a first-run user record the current commit without guessing between install, init, and generate?
  - did the first shareable summary look ready to paste into a PR?

If any answer is no for the default local path, the candidate is still at least
`WOUNDED`. If the path is broken, contradictory, or dead-end, keep `NO-GO`.

## Stop Conditions

Stop immediately and keep `NO-GO` if any of these happen:

1. a visible control dead-ends in the default local workflow
2. local-only mode fails open
3. multi-root isolation fails open
4. receipt repair targets the wrong commit
5. the zero-friction audit cannot be completed with real evidence

## Required Report Update

After the blocking pass:

1. update `DEEP_SMOKE_RUN_2026-03-15.md`
2. replace the blocking `WOUNDED` and `FAIL` verdicts with operator verdicts
3. fill the `Evidence saved` column with screenshot names or exact notes
4. keep the final verdict at `NO-GO` unless every blocking item above is cleared

For the current candidate, that report update is complete.
