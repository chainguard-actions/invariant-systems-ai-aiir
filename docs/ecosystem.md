# Where AIIR Fits

AIIR occupies a specific layer in the software supply chain security stack:
**authorship-level provenance** — recording *who or what* produced a code change,
with tamper-evident receipts.

It is not a replacement for build-provenance, attestation, or transparency-log tools.
It fills the gap *before* those systems kick in.

---

## The supply chain, annotated

```text
Developer writes code (with or without AI)
        │
        ▼
┌───────────────────┐
│  AIIR              │  ◀── Authorship provenance: was AI involved?
│  Receipt generated │      Content-addressed, locally verifiable.
└───────────────────┘
        │
        ▼
   git commit + push
        │
        ▼
┌───────────────────┐
│  CI/CD pipeline    │  ◀── Build provenance (SLSA), attestation (in-toto),
│  Build + test      │      signing (Sigstore), SBOM (CycloneDX/SPDX)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Artifact registry │  ◀── Transparency logs (SCITT, Rekor),
│  Release           │      vulnerability scanning, policy gates
└───────────────────┘
```

AIIR operates at the top of this pipeline. By the time code reaches the build
system, the authorship context is already captured.

---

## System-by-system comparison

| System | Layer | What it proves | Relationship to AIIR |
|--------|-------|---------------|---------------------|
| **[SLSA](https://slsa.dev)** | Build provenance | *How* an artifact was built, from which source | AIIR receipts are source-level evidence that can be attached to broader source or build provenance. AIIR does not address build isolation or hermeticity. |
| **[in-toto](https://in-toto.io)** | Supply chain layout | That each step in a build layout was performed | AIIR can be wrapped in an in-toto-style Statement and predicate model. See the public adapter note before making stronger compatibility claims for any specific ecosystem. |
| **[SCITT](https://scitt.io)** | Transparency ledger | That a claim was registered in a tamper-evident log | AIIR receipts are valid SCITT claims (content-addressed, signable). AIIR does not operate a transparency log. |
| **[Sigstore](https://sigstore.dev)** | Signing infrastructure | *Who* signed an artifact (identity binding via OIDC) | AIIR uses Sigstore for receipt signing (`--sign`). Sigstore does not generate receipts. |
| **[OpenSSF Scorecard](https://scorecard.dev)** | Project health | Security posture of an OSS repository | Orthogonal. Scorecard measures project practices; AIIR records per-commit authorship provenance. |
| **Git `Co-authored-by`** | Commit metadata | Free-text annotation (no integrity guarantee) | AIIR reads trailers as input signals, then wraps them in a content-addressed, verifiable receipt. Trailers alone are not tamper-evident. |
| **EU AI Act** | Regulation | Traceability requirements for AI systems | AIIR provides machine-verifiable evidence of AI involvement at the commit level. It does not implement full AI Act compliance on its own. |

---

## What AIIR does not do

Being clear about scope prevents category confusion:

- **Does not replace SLSA.** AIIR covers authorship provenance, not build provenance.
- **Does not operate a log.** Receipts are local files. Use SCITT or Rekor for transparency-log recording.
- **Does not detect hidden AI usage.** AIIR records what is *declared*. Undisclosed Copilot inline completions are not captured unless the developer or tool declares them.
- **Does not perform vulnerability scanning.** That's a different tool entirely.
- **Does not require a hosted service.** Verification is local-first and offline-capable.

---

## Complementary stack (example)

A team that wants full supply chain coverage might combine:

1. **AIIR** — authorship provenance (commit-level)
2. **Sigstore** — identity binding (signing)
3. **SLSA + in-toto** — build provenance (pipeline-level)
4. **CycloneDX / SPDX** — dependency provenance (SBOM)
5. **SCITT / Rekor** — transparency log (public record)

AIIR's `--sign --in-toto` mode produces artifacts that are already compatible
with steps 2 and 3.

---

## Public adapter notes

The public website carries narrow ecosystem adapter notes designed for outreach,
issue links, and public discussion:

- [Ecosystem hub](https://invariantsystems.io/ecosystem/)
- [Witness attestor note](https://invariantsystems.io/ecosystem/witness-attestor/)
- [GUAC ingestor note](https://invariantsystems.io/ecosystem/guac-ingestor/)
- [AMPEL policy note](https://invariantsystems.io/ecosystem/ampel-policy/)
- [Predicate mapping note](https://invariantsystems.io/ecosystem/predicate-mapping/)
- [gittuf policy note](https://invariantsystems.io/ecosystem/gittuf-policy/)
- [Sigstore bundle note](https://invariantsystems.io/ecosystem/sigstore-bundle/)
- [SLSA source track note](https://invariantsystems.io/ecosystem/slsa-source-track/)

Use those pages as the public explainer layer. Use this repo for reviewable
specification, implementation, and issue discussion.

---

## Further reading

- [SPEC.md](../SPEC.md) — normative specification
- [agent-receipt-contract.md](agent-receipt-contract.md) — public draft of the AIIR agent-receipt profile
- [THREAT_MODEL.md](../THREAT_MODEL.md) — STRIDE/DREAD analysis
- [verify-independently.md](verify-independently.md) — verify receipts without trusting AIIR
- [guide-security-team.md](guide-security-team.md) — integration guide for security teams
