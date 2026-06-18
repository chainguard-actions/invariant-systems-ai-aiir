# This verifies. Why does strict fail?

This directory is intentionally small.

The same commit receipt can be:

- valid at the integrity layer
- rejected at the release-policy layer

That is the whole claim.

## Files

- `unsigned/receipt.json`: verifies cleanly
- `signed/receipt.json`: byte-identical copy of `unsigned/receipt.json`
- `signed/receipt.json.sigstore`: real Sigstore bundle matching `signed/receipt.json`

The `unsigned/` and `signed/` directories carry the same receipt bytes. The only difference is that `signed/` also contains the real `.sigstore` sidecar.

## Run it

Run these commands from inside this directory.
If you are in the full repo checkout, first `cd examples/verify-pass-strict-fail`.
The `PYTHONPATH=../..` prefix forces Python to use the AIIR code from this
checkout rather than any older installed package.

```bash
PYTHONPATH=../.. python3 -m aiir --verify unsigned/receipt.json --explain
PYTHONPATH=../.. python3 -m aiir --verify-release --receipts unsigned/ --policy strict
PYTHONPATH=../.. python3 -m aiir --verify-release --receipts signed/ --policy strict
```

If you are in the full AIIR checkout and want to confirm the sidecar itself is
a real matching bundle, you can also run:

```bash
python3 ../../scripts/check_rekor_bundle.py \
  --artifact signed/receipt.json \
  --bundle signed/receipt.json.sigstore
```

## What to notice

1. `unsigned/receipt.json` passes integrity verification.
2. `unsigned/` still fails strict release verification with `require_signing`.
3. `signed/` passes strict policy.
4. `signed/receipt.json.sigstore` is a real bundle matching the same receipt bytes.

The core receipt did not change.

- The receipt JSON bytes are identical in both directories.
- `content_hash` is the same in both directories.
- `receipt_id` is the same in both directories.

Only the evidence tier changed.

The claim here is simple:

> A pipeline can prove the receipt is intact and still reject it as insufficient release evidence.
