# AIIR Ledger Snapshot

This directory is a checked-in local ledger snapshot on the `main` branch.

It exists so the repository can demonstrate the default `.aiir/` CLI layout,
ship reproducible local verification examples, and keep a concrete ledger shape
in the public tree.

It is **not** the live CI dogfood feed.

The live GitHub Actions dogfood receipts are published separately on the public
[`receipts` branch](https://github.com/invariant-systems-ai/aiir/tree/receipts).
That branch carries the current signed receipt artifacts emitted by
`.github/workflows/dogfood.yml`, including:

- `*.json` receipt files
- `*.cbor` sidecars
- `*.json.sigstore` bundles

If you want to inspect or verify the live CI feed, start from the `receipts`
branch. If you want to inspect the default local ledger layout used by the CLI,
start from this directory.
