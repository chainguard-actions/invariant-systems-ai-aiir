# Adoption Guide: Security Team

**Goal: evaluate AIIR's trust properties, verify independently, integrate
into your compliance or audit workflow.**

You are evaluating AIIR for adoption or reviewing evidence produced by teams
that already use it. You need to know exactly what AIIR proves, what it doesn't,
and how to verify claims without trusting the tool itself.

---

## What AIIR proves

| Property                          | Mechanism                                                     | Strength                                             |
| --------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------- |
| **Integrity**                     | Content-addressed SHA-256 hash over canonical JSON            | Deterministic — same input always produces same hash |
| **Tamper evidence**               | Receipt ID derived from content hash                          | Any modification breaks verification                 |
| **Declared AI involvement**       | Heuristic scan of commit metadata (trailers, author, message) | Records what is declared, not what is hidden         |
| **Non-repudiation** (signed only) | Sigstore keyless signing (Fulcio + Rekor)                     | OIDC identity binding via transparency log           |
| **Provenance** (signed only)      | CI workflow identity embedded in Sigstore certificate         | Ties receipt to specific repo, workflow, and commit  |

## What AIIR does not prove

| Gap                   | Why                                                                                           |
| --------------------- | --------------------------------------------------------------------------------------------- |
| **Undeclared AI use** | Copilot inline completions, ChatGPT copy-paste, and agentic sessions leave no commit metadata |
| **Code correctness**  | AIIR receipts record authorship signals, not code quality                                     |
| **Human review**      | A receipt shows who committed, not who reviewed                                               |
| **Absence of AI**     | `is_ai_authored: false` means no signals detected, not that AI was not used                   |

See [THREAT_MODEL.md](../THREAT_MODEL.md) for the full STRIDE/DREAD analysis.

---

## Verify independently

You do not need to trust AIIR to verify its claims. Every verification step
uses public artifacts and standard tools.

### 1. Verify a receipt's integrity (offline)

```bash
pip install aiir
aiir --verify receipt.json --explain
```

Or verify without the CLI — the algorithm is:

1. Parse the JSON receipt
2. Extract the core fields (type, schema, version, commit, ai_attestation, provenance)
3. Serialize as canonical JSON (sorted keys, no whitespace)
4. SHA-256 hash the canonical bytes
5. Compare against `content_hash` and derive `receipt_id`

The algorithm is specified in [SPEC.md §8](../SPEC.md) with
[25 core conformance test vectors](../schemas/test_vectors.json).

### 2. Verify a Sigstore signature (requires network)

```bash
pip install aiir[sign]

# Basic — checks signature validity
aiir --verify receipt.json --verify-signature

# Recommended — pin to a specific CI identity
aiir --verify receipt.json --verify-signature \
  --signer-identity "https://github.com/OWNER/REPO/.github/workflows/aiir.yml@refs/heads/main" \
  --signer-issuer "https://token.actions.githubusercontent.com"
```

Without `--signer-identity`, verification accepts any valid Sigstore signer.
Always pin in production.

### 3. Verify published release evidence

```bash
# Recommended public release gate
python scripts/verify-release-evidence.py 1.5.1
```

That checks three public surfaces together:

- PEP 740 attestations for every wheel and sdist on PyPI
- `release-attest.json` and `release-attest.md` on the GitHub release, including
  the digest bindings back to the published artifacts, attached
  `.publish.attestation` files, raw `rekor-*.json` entries, and the
  `*.intoto.jsonl` provenance bundles
- the CycloneDX SBOM asset on the GitHub release

```bash
# Using GitHub's attestation API
gh attestation verify aiir-1.5.1-py3-none-any.whl \
  --repo invariant-systems-ai/aiir

# Using AIIR's own verification script
python scripts/verify-pypi-provenance.py --strict

# Or query PyPI's Integrity API directly
curl -s https://pypi.org/integrity/aiir/1.5.1/aiir-1.5.1-py3-none-any.whl/provenance \
  | python3 -m json.tool
```

Every AIIR release has PEP 740 digital attestations (SLSA provenance + PyPI
Publish predicates) signed via Trusted Publishing (OIDC, no static tokens).

If a release also ships offline transparency material, you can verify the Rekor
proofs and witness cosignatures without any network access:

```bash
aiir --artifact dist/aiir-1.5.1-py3-none-any.whl \
  --rekor-bundle dist/rekor-bundle.json \
  --trust-root aiir-trust.json \
  --witnessed-checkpoint dist/witnessed-checkpoint.txt \
  --require-witnesses release
```

That path uses the published `aiir.rekor.bundle.v1` and `aiir.trust.v1`
documents plus a raw witnessed checkpoint note. It is separate from the public
networked `verify-release-evidence.py` gate.

For AIIR's own GitHub releases, the release pipeline now publishes
per-artifact `*.rekor-bundle.json` assets plus `VERIFY-OFFLINE.md`. Those
assets give you the Rekor-side offline bundle directly. Full witness quorum
verification still requires a trust root and witnessed checkpoint from the
external witness layer you trust. The repo-owned automation for those assets
lives in the dedicated
[.github/workflows/offline-rekor-release.yml](../.github/workflows/offline-rekor-release.yml)
workflow.

If you want a minimal operator example for a pinned `2-of-3` witness quorum,
start with [examples/witness-quorum/policy.yaml](../examples/witness-quorum/policy.yaml),
[examples/witness-quorum/trust-root.example.json](../examples/witness-quorum/trust-root.example.json),
and [examples/witness-quorum/VERIFY.md](../examples/witness-quorum/VERIFY.md).
The draft publication workflow at
[examples/github-actions/.github/workflows/aiir-witnessed-release-draft.yml](../examples/github-actions/.github/workflows/aiir-witnessed-release-draft.yml)
shows how to package those files as release assets.

### 4. Verify the test suite

```bash
git clone https://github.com/invariant-systems-ai/aiir && cd aiir
pip install -e ".[dev]"
pytest --cov=aiir --cov-fail-under=100
```

100% line coverage is enforced. 2,214 collected tests across Python 3.9–3.13.

### 5. Check OpenSSF Scorecard

Visit [scorecard.dev/viewer/?uri=github.com/invariant-systems-ai/aiir](https://scorecard.dev/viewer/?uri=github.com/invariant-systems-ai/aiir) — automated assessment of branch protection, SAST, dependency management, and signing.

---

## Trust tiers

| Tier          | What you get                                     | Verify with                                              |
| ------------- | ------------------------------------------------ | -------------------------------------------------------- |
| **Unsigned**  | Hash integrity — detects modification            | `aiir --verify`                                          |
| **Signed**    | + OIDC identity binding via Sigstore             | `aiir --verify --verify-signature --signer-identity ...` |
| **Enveloped** | + in-toto Statement v1 wrapper (SLSA-compatible) | Standard in-toto/SLSA verification tooling               |

For audit evidence, require **Signed** or **Enveloped** receipts. Unsigned
receipts are developer convenience — anyone who can run `aiir` on the same
commit can recreate a valid receipt.

---

## Policy evaluation

AIIR includes a policy engine with three named presets:

| Preset       | Enforcement | Signing     | Max AI % |
| ------------ | ----------- | ----------- | -------- |
| `strict`     | Hard-fail   | Required    | 50%      |
| `balanced`   | Soft-fail   | Recommended | 80%      |
| `permissive` | Warn-only   | Optional    | 100%     |

Policy files are JSON, committed to the repo, and evaluated in CI:

```bash
aiir --check --policy strict
```

Release-scoped evaluation produces a Verification Summary Attestation (VSA):

```bash
aiir --verify-release --receipts .aiir/receipts.jsonl --policy strict --emit-vsa
```

The VSA is an [in-toto Statement v1](https://in-toto.io/Statement/v1)
with a `https://slsa.dev/verification_summary/v1` predicate.

---

## Integration patterns

### SOC 2 / audit evidence

1. Enable Sigstore signing in CI (`sign: true`, the default)
2. Apply `strict` policy preset
3. Archive `.receipts/` and VSA artifacts as audit evidence
4. Pin signer identity to your CI workflow for non-repudiation

### EU AI Act compliance evidence

1. Use enveloped receipts (`--in-toto --sign`)
2. Policy preset: `strict`
3. Export evidence packs for regulatory reviewers

### Downstream verification

A skeptical third party receiving your software can:

1. Fetch receipts from your releases or `.aiir/` directory
2. Verify each receipt's content hash (offline, no trust in AIIR needed)
3. Verify Sigstore signatures against the transparency log
4. Check the VSA for policy evaluation results

No account, no API key, no network dependency for unsigned verification.

---

## Supply chain security

| Control                     | Mechanism                                    |
| --------------------------- | -------------------------------------------- |
| Zero runtime dependencies   | Nothing to compromise — stdlib only          |
| Trusted Publishing          | OIDC tokens, no static PyPI API keys         |
| SLSA provenance             | Every wheel has a build attestation          |
| SHA-pinned CI dependencies  | All `uses:` reference full 40-char SHAs      |
| CycloneDX SBOM              | Machine-readable BOM on every GitHub Release |
| Gitleaks + Bandit + Semgrep | Automated secret and vulnerability scanning  |

---

## Quick reference

| Task                  | Command                                             |
| --------------------- | --------------------------------------------------- |
| Verify a receipt      | `aiir --verify receipt.json --explain`              |
| Verify signature      | `aiir --verify receipt.json --verify-signature`     |
| Pin signer            | `--signer-identity <url> --signer-issuer <issuer>`  |
| Check PyPI provenance | `python scripts/verify-pypi-provenance.py --strict` |
| Run full test suite   | `pytest --cov=aiir --cov-fail-under=100`            |
| Evaluate policy       | `aiir --check --policy strict`                      |
| Release verification  | `aiir --verify-release --emit-vsa --policy strict`  |
