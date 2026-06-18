# NISQ Research-Evidence Receipts

> Public case study for the AIIR research-evidence receipt profile.

The first public bridge for this profile is the NISQ readiness capsule from the
private Invariant Systems research repository.

It shows the intended separation of concerns:

- the private research repository keeps the scientific program, claim register,
  and evidence corpus under its own governance
- the private research repository exports a deterministic receipt for the public-safe
  claim boundary
- AIIR verifies that exported receipt without embedding the quantum core logic

---

## Why NISQ is the first bridge

The NISQ readiness lane is the safest initial public bridge because it already
has all of the following:

- a governed claim entry with explicit non-claims
- a public-safe publication capsule
- replayable evidence artifacts and verifier scripts
- a clear boundary between evidence-contract portability and broader scientific claims

By contrast, active theorem lanes and private finite-volume toy work remain
private by default.

---

## What the receipt says

The exported research-evidence receipt binds:

- the governed claim id for the NISQ readiness standard
- the declared public evidence directory and migration receipt
- the declared verifier paths used for replay
- the disclosure boundary: public-safe, not IP-sensitive
- the next governance gate after the current verified state

The receipt does not claim:

- quantum advantage
- fault tolerance
- loophole-free Bell testing
- multi-vendor universality

Those limits stay explicit in both the research claim register and the public
capsule itself.

---

## Optional quantum extension

The profile allows a narrow optional namespace such as
`extensions.io.invariantsystems.quantum`.

In the NISQ case, that extension is limited to evidence-contract framing,
including details such as:

- the IBM-only scope of the frozen statistical corpus
- the presence of AWS Braket and Azure Quantum adapter checks as portability checks
- the rule that those adapter checks do not upgrade the IBM-only statistical claim

The extension carries receipt context. It does not carry quantum engine logic.

---

## Independent verification path

Once the research repository emits the receipt, a verifier can check it with the
public AIIR interface:

```bash
aiir --verify nisq-readiness-evidence-standard-2026-04-30.aiir.json
```

If verification succeeds, the verifier has confirmed that the exported public
claim record is structurally intact and content-addressed. They still evaluate
the underlying evidence on its own scientific merits.
