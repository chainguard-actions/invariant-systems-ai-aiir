# AIIR Residual Risk Boundary

AIIR is intentionally narrow.

That is a strength for verification, but it also means there are decisions the
system should not make on its own.

## What AIIR can decide reliably

- Whether a receipt's covered fields still match its `content_hash`.
- Whether a signed receipt verifies against Sigstore material and a pinned identity.
- Whether a configured policy passed or failed for the receipts it evaluated.
- Whether the declared AI context present in commit metadata was normalized into the receipt.

## What AIIR cannot safely decide on its own

### 1. Hidden AI use

If AI work leaves no durable commit marker, AIIR cannot prove absence.

That is why `is_ai_authored: false` means "no declared signal detected," not
"AI was definitely not used."

### 2. Code quality or security sufficiency

A valid receipt does not mean the code is correct, reviewed, safe, or ready to
ship. Provenance is not correctness.

### 3. Governance adequacy

AIIR can enforce a policy file, but it cannot decide whether `strict`,
`balanced`, or a custom threshold is the right business rule for a given repo.

### 4. Reviewer intent

AIIR can record that a workflow or maintainer emitted evidence. It cannot infer
whether the human reviewer understood the change, accepted the risk, or should
have blocked it.

### 5. History legitimacy outside the receipt boundary

If the underlying branch was rewritten, squashed, or selectively disclosed,
AIIR can only reason about the commit object it was asked to receipt or verify.

## Accepted residuals from the threat model

The current threat model keeps three residual classes visible:

| Residual | Why it remains | Practical answer |
|---|---|---|
| Unsigned receipt fabrication | Integrity without signing does not prove origin | Use Sigstore signing for compliance or non-repudiation |
| Commit history rewrite outside AIIR | Git history itself can be rewritten before or after receipting | Pin reviews and releases to commit SHAs and signed evidence |
| Undeclared agent-mode or chat-based AI work | Many tools still do not leave durable git markers | Improve declaration discipline or use stronger capture surfaces |

See [THREAT_MODEL.md](../THREAT_MODEL.md#6-dread-risk-scoring-residual) for the
formal residual scoring.

## Safe automation boundary

AIIR is safe to automate for:

- receipt generation
- receipt verification
- signer verification
- policy evaluation
- CI release gating

AIIR should remain advisory, not autonomous, for:

- declaring that no AI was used
- deciding that code is safe to merge
- deciding that a review was sufficient
- deciding that a policy threshold is appropriate
- deciding that a release is acceptable despite conflicting evidence

## Operator rule

If AIIR is green but the human question is about intent, hidden use, business
acceptance, or code safety, AIIR is informing the decision, not making it.
