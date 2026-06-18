# AIIR VS Code UI Smoke Threat Model

This is the release-layer threat model for packaged-VSIX UX checks. It does not
replace the repository-wide security model in [../../../../THREAT_MODEL.md](../../../../THREAT_MODEL.md).

Use this document when deciding whether a smoke finding is a ship blocker.

## Verdicts

- `PASS`: the default local workflow is readable, coherent, and completes without guessing.
- `WOUNDED`: the workflow completes, but the user hits avoidable friction, unclear copy, or a detour that should be cleaned up.
- `FAIL`: the user hits a dead-end, contradictory state, wrong-target repair path, or a fail-open policy boundary.

## Immediate No-Go Triggers

- A visible control dead-ends in the default local workflow.
- Local-only or multi-root isolation fails open.
- Receipt repair targets the wrong commit or repository.
- Two visible surfaces disagree about repository state in the same scenario.

## Canonical References

- [Repository Threat Model](../../../../THREAT_MODEL.md)
- [Smoke Test Entry Point](SMOKE_TEST.md)
- [Blocking Deep Smoke Checklist](../release/BLOCKING_DEEP_SMOKE_CHECKLIST.md)
- [Recorded Deep Smoke Run](../release/DEEP_SMOKE_RUN_2026-03-15.md)
