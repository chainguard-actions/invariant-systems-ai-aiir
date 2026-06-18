# Verify a Witnessed AIIR Release Offline

This directory is the smallest release-attestation pack that matches AIIR's
current offline transparency verifier.

It is built around one log key plus three pinned witness keys with a `2-of-3`
release policy:

- `rekor-bundle.json` proves the artifact hash, inclusion proof, and checkpoint
- `aiir-trust.json` pins the log key and the three trusted witness keys
- `witnessed-checkpoint.txt` carries the witness cosignatures
- `VERIFY.md` tells consumers how to check the bundle without network access

## What to customize

1. Copy `policy.yaml` and `trust-root.example.json` into your release repo.
2. Replace every sample key id and public key with real values from your log and
   witness deployments.
3. Publish the four files listed above next to the wheel, sdist, and SBOM.

The YAML file is for operators. AIIR consumes the JSON trust root.

## Minimal acceptance policy

- Verify the artifact hash bound into the Rekor entry body.
- Verify the inclusion proof against the signed checkpoint.
- If a newer witnessed checkpoint is shipped, verify the consistency proof from
  the bundled checkpoint to the witnessed checkpoint.
- Require any `2-of-3` pinned witness cosignatures under the named `release`
  policy.

This is intentionally simple. AIIR's current verifier enforces the pinned
threshold. It does not currently express role constraints such as “at least one
public witness”; if you need that, enforce it in a separate release gate before
you publish the bundle.

## Verify with the AIIR CLI

```bash
aiir --artifact dist/aiir-1.7.0-py3-none-any.whl \
  --rekor-bundle dist/rekor-bundle.json \
  --trust-root dist/aiir-trust.json \
  --witnessed-checkpoint dist/witnessed-checkpoint.txt \
  --require-witnesses release
```

## Verify with the standalone helper

```bash
python3 scripts/check_rekor_bundle.py \
  --artifact dist/aiir-1.7.0-py3-none-any.whl \
  --bundle dist/rekor-bundle.json \
  --trust-root dist/aiir-trust.json \
  --witnessed-checkpoint dist/witnessed-checkpoint.txt \
  --require-witnesses release
```

## Publish alongside the release

Ship these files as release assets:

- `rekor-bundle.json`
- `aiir-trust.json`
- `witnessed-checkpoint.txt`
- `VERIFY.md`

Consumers can then verify the release offline with only the wheel, the offline
bundle, and the pinned trust root.

## Draft workflow

The matching publication skeleton lives at
`examples/github-actions/.github/workflows/aiir-witnessed-release-draft.yml`.
It is intentionally a draft: you replace one acquisition step with your own
Rekor v2 and witness client, then the rest of the workflow assembles and
publishes the AIIR-compatible offline bundle.
