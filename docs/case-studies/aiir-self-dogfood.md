# AIIR Generates Receipts for AIIR

> Public dogfood case study.
>
> Scope: how the AIIR project uses AIIR's own receipt format and verification
> flows in day-to-day development and release work.

AIIR is not asking other teams to trust an untested idea. This repository uses
AIIR's own receipt and verification surfaces on itself.

That matters for two reasons:

1. The public claims in the README stay anchored to visible artifacts.
2. The reference implementation is forced to live with its own ergonomics.

---

## What is actually dogfooded

AIIR uses its own public surfaces in five ways:

- the CLI generates and verifies receipts locally, and `main` carries a checked-in `.aiir/` snapshot for local-ledger examples
- the GitHub Action emits signed receipts in CI and publishes the live feed on the public `receipts` branch
- the commitment receipt surface binds public bundles and published digests that
  sit outside the git commit graph
- the GitLab CI component mirrors the same workflow on the GitLab side
- the MCP surface lets assistant-driven workflows emit or verify receipts from
  the same public contract

This is the exact adoption path described for downstream users. There is no
special private verifier and no separate internal-only receipt format.

---

## Public artifacts you can inspect

- the public [`receipts` branch](https://github.com/invariant-systems-ai/aiir/tree/receipts) for the live GitHub Action dogfood feed (`.json`, `.cbor`, `.sigstore`)
- the checked-in `.aiir/` directory on `main` as a local-ledger snapshot used in CLI and documentation examples
- [examples/commitment-receipt-bundle/](../../examples/commitment-receipt-bundle/)
  for a public signed digest-binding commitment receipt plus negative case
- [examples/commitment-directory-bundle/](../../examples/commitment-directory-bundle/)
  for a public signed directory-binding commitment receipt plus negative case
- [README.md](../../README.md) proof points for dogfooding, conformance, and
  release evidence
- [docs/implementers.md](../implementers.md) for the public implementers and
  pilots registry entry
- [GitHub Actions workflow history](https://github.com/invariant-systems-ai/aiir/actions/workflows/dogfood.yml) on the public repository
- `python scripts/verify-release-evidence.py <version>` for release-scoped
  verification of the published evidence bundle

Nothing in this case study depends on private infrastructure.

---

## What this has taught us

### 1. Declared provenance is the right first wedge

AIIR records declared AI involvement, not hidden AI usage. That sounds narrow,
but the dogfood experience reinforces why the wedge still matters.

The repository was built heavily with assistant help, yet the checked-in
`.aiir` snapshot on `main` still skews heavily `human` because tools like
chat-based assistants often do not leave trailers or equivalent declared
signals behind.

That is not a failure of the receipt format. It is the reason the broader
ecosystem needs portable declaration and evidence contracts.

### 2. Zero-dependency distribution matters

The public CLI and verifier stay easy to adopt because they remain local-first
and standard-library-only. Dogfooding keeps pressure on the project not to turn
basic verification into a hosted-service dependency.

### 3. One evidence shape across surfaces matters

The same core receipt semantics flow through local CLI use, CI automation,
public verification docs, and downstream wrappers such as in-toto statements.
Dogfooding is valuable because it exposes drift early if one surface starts to
behave differently from the rest.

---

## Limits of this case study

This is an internal dogfood case study published in the open. It is useful
because the artifacts are inspectable, but it is still not the same thing as a
third-party customer reference or an independent external implementation.

Those remain separate adoption milestones.

---

## Reproduce the basic check yourself

From a clone of the repository:

```bash
# Local ledger flow used in the CLI/docs
pip install aiir
aiir --pretty
aiir --verify .aiir/receipts.jsonl

# Release evidence surface
python scripts/verify-release-evidence.py 1.6.0
```

For the live CI dogfood feed, open the public `receipts` branch, download any
`.json` receipt from that branch, and run `aiir --verify <downloaded-file>`.

If those commands succeed, you have reproduced the public dogfood story using
the same public interfaces the project asks everyone else to trust.
