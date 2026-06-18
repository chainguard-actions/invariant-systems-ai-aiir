# AIIR -> AMPEL Policy Integration

Use AIIR receipts as policy inputs for AMPEL so a policy engine can reason
about declared AI authorship, receipt integrity, and release evidence without
re-parsing git history.

This directory is an adapter note, not a runtime dependency. AIIR stays
stdlib-only; AMPEL policy evaluators consume the receipt data that AIIR already
emits.

## How it works

AIIR produces content-addressed commit receipts. AMPEL policy rules can treat
those receipts as source-level facts:

```text
git commit
    |
    v
aiir --json --trailer      <- generates receipt + discoverable trailers
    |
    v
AIIR receipt               <- commit, AI attestation, provenance, extensions
    |
    v
AMPEL policy input         <- evaluate AI-authorship and verification policy
```

Use the public AMPEL adapter note for external discussion:

<https://invariantsystems.io/ecosystem/ampel-policy/>

## Receipt fields for policy inputs

| AIIR field | AMPEL policy use |
|---|---|
| `receipt_id` | Stable fact identifier for audit logs and policy decisions |
| `content_hash` | Integrity check for the receipt core |
| `commit.sha` | Commit subject for the policy decision |
| `commit.tree_sha` | Directory-state binding for anti-laundering checks |
| `commit.parent_shas` | DAG-position binding for branch/release policy |
| `ai_attestation.is_ai_authored` | Primary AI-authorship flag |
| `ai_attestation.authorship_class` | Human / AI-assisted / bot classification input |
| `ai_attestation.signals_detected` | Explainability and review-routing evidence |
| `provenance.generator` | Source surface: CLI, GitHub, GitLab, MCP, or editor |
| `extensions.agent_attestation` | Declared tool/model/run-context evidence |
| `extensions.tool_context` | Companion IDE or workflow context, such as GitLens |

## Example policy facts

An AMPEL policy adapter can normalize AIIR receipts into facts like:

```json
{
  "subject": "git:commit:0123456789abcdef0123456789abcdef01234567",
  "receipt_id": "g1-0123456789abcdef0123456789abcdef",
  "receipt_verified": true,
  "ai_authored": true,
  "authorship_class": "ai_assisted",
  "evidence_level": ["declared", "ide-context"],
  "generator": "aiir.github"
}
```

## Example policy questions

- Did every AI-assisted commit in a protected branch produce a valid AIIR receipt?
- Are GitLens Commit Composer commits receipted before merge?
- Are release candidates blocked when AI-assisted commits lack signed receipts?
- Which AI-authored commits require human review receipts before promotion?

## Boundaries

- AIIR does not execute AMPEL policies.
- AIIR does not replace a policy engine or approval workflow.
- Plain GitLens extension presence is companion context only; it is not AI
  authorship unless a Commit Composer action or explicit declaration is present.
- AMPEL policy decisions should verify receipt integrity before trusting receipt
  fields.

## References

- [AIIR Specification](../../SPEC.md)
- [AIIR ecosystem positioning](../../docs/integrations/ecosystem.md)
- [GitLens integration](../../docs/integrations/gitlens-integration.md)
- [Public AMPEL policy note](https://invariantsystems.io/ecosystem/ampel-policy/)
