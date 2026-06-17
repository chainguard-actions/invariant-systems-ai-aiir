# AIIR Research-Evidence Receipt Profile

> Draft profile for portable receipts covering governed research claims and their
> evidence surfaces.
>
> Status: public draft (v0.1). Verify-only in AIIR core.

AIIR can verify research-evidence receipts without importing the underlying
science engine into AIIR itself.

That is the intended boundary:

- the research repository governs claims, evidence paths, verifier paths, and
  disclosure status
- the research repository emits deterministic receipts from those governed
  surfaces
- AIIR verifies the resulting receipt structure and content-addressed integrity

This profile is the first public bridge for research programs that already have
clear claim boundaries and public-safe evidence surfaces.

Machine-readable artifacts:

- [schemas/research_evidence_receipt.v0.1.schema.json](../schemas/research_evidence_receipt.v0.1.schema.json)
- [schemas/research_evidence_receipt_vectors.v0.1.schema.json](../schemas/research_evidence_receipt_vectors.v0.1.schema.json)
- [schemas/test-vectors/research_evidence_receipt_vectors.v0.1.json](../schemas/test-vectors/research_evidence_receipt_vectors.v0.1.json)

---

## What this profile binds

One research-evidence receipt binds:

1. one governed research claim
2. the declared evidence artifacts attached to that claim
3. the declared verifier paths used to review that claim
4. the governance boundary for disclosure and next review gate

The receipt proves that the exported record has not been tampered with after it
was emitted. It does not prove the underlying theorem, physics claim, or
experimental result by itself.

---

## Non-goals

This profile does not:

- turn AIIR into a quantum or mathematics engine
- force private research repositories to expose non-public claims
- replace scientific peer review or domain-specific verification
- declare that all research evidence is safe to publish

The public AIIR surface is verify-only here on purpose.

---

## Core record

The record is one JSON object with these logical sections:

- `subject`
- `claim`
- `evidence`
- `governance`
- `proof`

### Minimal example

```json
{
  "contract_version": "aiir/research_evidence_receipt.v0.1",
  "record_id": "r1-d086b895035685db48f5282eddaa2851",
  "timestamp": "2026-04-30T00:00:00Z",
  "subject": {
    "kind": "research_claim",
    "repo": "invariant-systems-research",
    "program_id": "02-nisq-readiness",
    "claim_id": "nisq-readiness-evidence-standard-2026-04-30",
    "title": "Evidence-first NISQ readiness standard"
  },
  "claim": {
    "status": "verified",
    "summary": "Evidence-first NISQ readiness capsule with replayable IBM-backed analysis and portable adapter validation.",
    "non_claims": [
      "not quantum advantage",
      "not fault tolerance",
      "not multi-vendor universality"
    ],
    "last_reviewed": "2026-04-30"
  },
  "evidence": {
    "artifacts": [
      {
        "type": "directory",
        "ref": "3-proof/3d-evidence/quantum/02-nisq-readiness/",
        "digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
        "role": "evidence"
      }
    ],
    "verifiers": [
      {
        "type": "file",
        "ref": "3-proof/3p-deliverable/publications/arxiv/02-nisq-readiness/anc/verify_chsh.py",
        "digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
        "role": "verifier"
      }
    ]
  },
  "governance": {
    "public_safe": true,
    "ip_sensitive": false,
    "disclosure_tier": "public",
    "next_gate": "Internal publication signoff and DOI deposit using the capsule release checklist."
  },
  "proof": {
    "canonicalization": "aiir-canon-0",
    "content_hash": "sha256:d086b895035685db48f5282eddaa28512f805056a5fe836df002b975b826d82e",
    "signature": null
  },
  "extensions": {
    "io.invariantsystems.quantum": {
      "modality": "nisq",
      "adapter_validation": ["aws-braket", "azure-quantum"]
    }
  }
}
```

---

## Canonicalization and IDs

The profile uses the same canonicalization family as the AIIR commit and agent
profiles: `aiir-canon-0`.

For v0.1, the record core is:

- `contract_version`
- `timestamp`
- `subject`
- `claim`
- `evidence`
- `governance`
- `proof.canonicalization`

As with the draft agent profile, `extensions` are excluded from the record core
in v0.1 so that domain-specific metadata can evolve without destabilizing basic
verification.

The identifier is:

```text
record_id = "r1-" + hex(SHA-256(canonical_json(record_core)))[:32]
```

---

## Privacy and disclosure rule

This profile is designed for selective export from governed research repos.

The recommended default is:

- emit only claims already marked `public_safe: true`
- keep private or IP-sensitive lanes private unless an operator explicitly opts in
- use extensions only for narrow adapter metadata, not for embedding private notebooks,
  prompts, or large scientific payloads

That keeps AIIR on the public provenance boundary instead of turning it into a
replica of the private research repository.

---

## Verify-only posture in AIIR

AIIR verifies research-evidence receipts but does not generate them in the
public CLI by default. The emitting repository owns its own governance logic.

That mirrors the existing inference-receipt posture: public AIIR core can check
integrity without claiming ownership of every receipt emitter.

---

## First public bridge

The first public bridge case is the NISQ readiness capsule from the Invariant
Systems research program. See the companion case study:

- [docs/case-studies/nisq-research-evidence.md](case-studies/nisq-research-evidence.md)
