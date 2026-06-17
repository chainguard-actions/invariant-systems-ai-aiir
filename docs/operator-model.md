# AIIR Operator Model

This is the shortest human-facing model of AIIR.

If you need the full argument, read [THREAT_MODEL.md](../THREAT_MODEL.md),
[SECURITY.md](../SECURITY.md), and the persona guides in [README.md](../README.md).

## What AIIR is for

AIIR answers three narrow questions:

- Was declared AI context bound to a specific commit in a tamper-evident way?
- If the receipt was signed, which workflow identity emitted it?
- Did the current receipts satisfy the configured policy gate?

AIIR does not answer three other questions:

- Was AI used if no durable declaration exists?
- Is the code correct, safe, or adequately reviewed?
- Is the chosen policy threshold the right governance decision?

## The objects that matter

| Object | Why it matters | Failure if wrong |
|---|---|---|
| Commit | The software change under review | You are reasoning about the wrong code |
| Receipt | The tamper-evident record for that commit | Evidence can be modified or fabricated |
| Signature | Optional authenticity layer over the receipt | You cannot prove who emitted the receipt |
| Policy | The pass/fail threshold for a repo or release | A green gate may still mean the wrong governance choice |

## What can fail

| Layer | Typical failure | What it means |
|---|---|---|
| Declaration | AI work lands without durable markers | AIIR may classify the commit as `human` even if AI was used |
| Integrity | `aiir --verify` fails | The receipt or its covered commit context no longer matches |
| Authenticity | Receipt is unsigned or signature verification fails | You have tamper evidence only, not trusted origin |
| Policy | `aiir --check` or `--verify-release` fails | The repo's configured gate did not accept the evidence |
| Release hygiene | `scripts/ci-local.sh required` fails | The candidate is not ready to publish or merge as-is |

## What blocks it

| Blocker | Where it shows up | Immediate consequence |
|---|---|---|
| Missing declaration | Receipt says `AI: no` for known AI-assisted work | Disclosure is incomplete |
| Unsigned receipts in a signed flow | CLI warning, policy failure, or audit rejection | Evidence is not strong enough for compliance claims |
| Receipt tampering or commit mismatch | `aiir --verify` fails | Stop treating that receipt as valid evidence |
| Wrong signer identity | `--verify-signature` fails when identity is pinned | The receipt may be validly signed by the wrong workflow |
| Public-surface drift | Local CI or release checks fail on version mismatch | Release packet is inconsistent across repo and website surfaces |

## What do I do next

| Situation | Next action |
|---|---|
| Receipt verification fails | Stop. Do not use the receipt as evidence. Regenerate from the expected commit or investigate tampering/history rewrite. |
| Receipt is unsigned but the workflow needs provenance | Re-run in CI with signing enabled and verify with pinned signer identity. |
| Known AI use was classified as `human` | Treat it as a disclosure gap, not proof of no AI. Add durable declaration or use a capture surface that records it. |
| Policy gate fails | Inspect the failing receipts, decide whether the code/disclosure is wrong or the policy is wrong, then rerun the gate. |
| Local preflight fails | Fix the failing test, coverage, version-sync, or package-smoke issue before merge or release. |

## Escalate immediately when

- A signed receipt fails integrity or signature verification.
- A release candidate passes local review but fails public-surface or provenance checks.
- Contributors are treating unsigned receipts as proof of origin.
- A repo repeatedly shows `human` receipts for work that is known to involve chat or agent tools.

## One-line mental model

AIIR is a receipt system for declared AI involvement.

It is strong on tamper evidence, optional signing, and policy evaluation.
It is intentionally weak on hidden-use detection, code quality judgment, and
governance decisions that still require a human owner.
