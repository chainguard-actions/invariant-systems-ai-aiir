# AIIR VS Code Smoke Test Entry Point

This page keeps the public smoke-test entrypoint stable while the detailed
release packet lives under `../release/`.

Use these canonical documents for the current packaged-VSIX release path:

- [Blocking Deep Smoke Checklist](../release/BLOCKING_DEEP_SMOKE_CHECKLIST.md)
- [Deterministic Smoke Coverage](../release/DETERMINISTIC_SMOKE_COVERAGE.md)
- [Recorded Deep Smoke Run](../release/DEEP_SMOKE_RUN_2026-03-15.md)

Minimum release rule:

1. Run the packaged VSIX, not only the source checkout.
2. Pair the manual operator pass with the deterministic checks.
3. Keep the candidate blocked if the default local path dead-ends, contradicts itself, or fails open.
