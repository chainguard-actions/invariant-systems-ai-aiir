# Verifier Instructions

This bundle is self-contained and verifiable offline. No account, API key, or
network access is required for content-hash verification.

Release: `HEAD`
Commit range: `(all receipts)`

## 1. Confirm the manifest is intact

```bash
sha256sum -c manifest.sha256
```

## 2. Re-hash every artifact against the manifest

```bash
python3 - <<'PY'
import hashlib, json, pathlib
manifest = json.loads(pathlib.Path("manifest.json").read_text())
ok = True
for entry in manifest["artifacts"]:
    data = pathlib.Path(entry["path"]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        ok = False
        print("MISMATCH", entry["path"])
print("all artifacts match" if ok else "ARTIFACT MISMATCH")
PY
```

## 3. Verify each receipt's content hash (no trust in AIIR required)

```bash
for f in receipts/*.json; do
  python3 -m aiir --verify "$f" --explain || true
done
```

## 4. Re-run the release policy decision

```bash
python3 -m aiir --verify-release \
  --receipts receipts/ \
  --policy policy.json \
  --emit-vsa
```

Compare the resulting decision with `verify-release.json` and `vsa.intoto.json`.

## 5. (Optional) Verify Sigstore signatures

If `signatures/` contains `*.sigstore` bundles, verify them against the matching
receipt with `python -m sigstore verify identity` or
`scripts/check_rekor_bundle.py`.

## Boundary

- AIIR records declared AI involvement. It does not prove hidden AI use.
- A commit without a receipt is not proof that no AI assistance was used.
- A release bundle is not a build-provenance, SBOM, or SLSA replacement; it adds the AI-involvement layer to that supply-chain evidence stack.
