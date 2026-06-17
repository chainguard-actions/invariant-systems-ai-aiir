#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""DSSE ↔ JCS conformance harness.

Production-focused conformance checks for DSSE vectors under test-vectors/.

Outputs:
- conformance/mismatches.json (machine-readable findings)
- conformance/report.txt (human-readable summary)
- conformance/canonical/** (canonicalized payload bytes)
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import hmac
import json
import pathlib
import subprocess
from typing import Any


ROOT = pathlib.Path("test-vectors")
OUT_DIR = pathlib.Path("conformance")
CANON_DIR = OUT_DIR / "canonical"


@dataclasses.dataclass
class Verdict:
    path: str
    bundle: bool
    cosign_ok: bool | None
    sigstore_py_ok: bool | None
    payload_json_exists: bool
    dsse_payload_b64_valid: bool
    payload_digest_match: bool | None
    canonicalization_ok: bool
    mismatch: bool
    failures: list[str]
    notes: list[str]


class ConformanceError(RuntimeError):
    """Raised on malformed vector data."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DSSE↔JCS conformance checks")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail when no *.dsse vectors are found.",
    )
    parser.add_argument(
        "--cosign-timeout-seconds",
        type=int,
        default=30,
        help="Timeout for cosign verify-blob execution (default: 30).",
    )
    return parser.parse_args()


def jcs(data: bytes) -> bytes:
    """Deterministic canonical JSON serializer used for CI parity checks.

    This implementation provides stable canonical bytes for object key ordering,
    separators, UTF-8 encoding, and NaN/Infinity rejection.
    """
    obj = json.loads(data.decode("utf-8"))
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def load(path: pathlib.Path) -> bytes:
    return path.read_bytes()


def write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_dsse_payload(envelope_path: pathlib.Path) -> tuple[bytes, dict[str, Any]]:
    raw = load(envelope_path)
    try:
        env = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ConformanceError(f"invalid DSSE JSON: {exc}") from exc

    if not isinstance(env, dict):
        raise ConformanceError("DSSE envelope must be a JSON object")

    payload_b64 = env.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise ConformanceError("DSSE envelope missing non-empty string payload")

    try:
        payload = base64.b64decode(payload_b64, validate=True)
    except Exception as exc:
        raise ConformanceError(f"invalid base64 DSSE payload: {exc}") from exc

    payload_type = env.get("payloadType")
    if not isinstance(payload_type, str) or not payload_type:
        raise ConformanceError("DSSE envelope missing non-empty payloadType")

    signatures = env.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        raise ConformanceError("DSSE envelope missing non-empty signatures list")

    for idx, sig_entry in enumerate(signatures):
        if not isinstance(sig_entry, dict):
            raise ConformanceError(f"DSSE signature entry {idx} must be an object")
        sig = sig_entry.get("sig")
        if not isinstance(sig, str) or not sig:
            raise ConformanceError(f"DSSE signature entry {idx} missing non-empty sig")

    return payload, env


def cosign_verify_blob(
    blob_path: pathlib.Path,
    bundle_path: pathlib.Path,
    timeout_seconds: int,
) -> tuple[bool, str]:
    cmd = ["cosign", "verify-blob", "--bundle", str(bundle_path), str(blob_path)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    stderr = proc.stderr.strip()
    return proc.returncode == 0, stderr


def py_sigstore_verify_blob_with_bundle(
    blob_path: pathlib.Path,
    bundle_path: pathlib.Path,
) -> tuple[bool, str]:
    try:
        from sigstore.models import Bundle
        from sigstore.verify import Verifier
        from sigstore.verify.policy import UnsafeNoOp

        bundle = Bundle.from_json(bundle_path.read_text(encoding="utf-8"))
        verifier = Verifier.production()
        verifier.verify_artifact(blob_path.read_bytes(), bundle, UnsafeNoOp())
    except Exception as exc:  # pragma: no cover - runtime integration path
        return False, str(exc)
    return True, ""


def analyze_vector(env_path: pathlib.Path, timeout_seconds: int) -> Verdict:
    base = env_path.with_suffix("")
    payload_json_path = pathlib.Path(f"{base}.json")
    bundle_path = pathlib.Path(f"{base}.bundle")

    failures: list[str] = []
    notes: list[str] = []

    dsse_payload: bytes | None = None
    dsse_payload_b64_valid = False
    try:
        dsse_payload, _ = decode_dsse_payload(env_path)
        dsse_payload_b64_valid = True
    except ConformanceError as exc:
        failures.append(str(exc))

    payload_digest_match: bool | None = None
    canonicalization_ok = True

    if payload_json_path.exists():
        source = load(payload_json_path)
        canonical = jcs(source)
        rel_payload = payload_json_path.relative_to(ROOT)
        write(CANON_DIR / rel_payload, canonical)

        if dsse_payload is not None:
            payload_digest_match = hmac.compare_digest(
                sha256_hex(canonical),
                sha256_hex(dsse_payload),
            )
            if not payload_digest_match:
                failures.append("canonical payload digest does not match DSSE payload digest")

    else:
        notes.append("payload .json not present")

    cosign_ok: bool | None = None
    cosign_err = ""
    sigstore_ok: bool | None = None
    sigstore_err = ""

    if bundle_path.exists():
        try:
            cosign_ok, cosign_err = cosign_verify_blob(env_path, bundle_path, timeout_seconds)
        except subprocess.TimeoutExpired:
            cosign_ok = False
            cosign_err = "cosign verification timed out"
            failures.append(cosign_err)

        sigstore_ok, sigstore_err = py_sigstore_verify_blob_with_bundle(env_path, bundle_path)
        if not sigstore_ok:
            failures.append(f"sigstore-python verify failed: {sigstore_err}")
        if cosign_ok is False and cosign_err:
            failures.append(f"cosign verify failed: {cosign_err}")
    else:
        notes.append("bundle not present")

    mismatch = (
        cosign_ok is not None
        and sigstore_ok is not None
        and cosign_ok != sigstore_ok
    )
    if mismatch:
        failures.append("cosign and sigstore-python verdict mismatch")

    if failures:
        canonicalization_ok = False

    return Verdict(
        path=str(env_path),
        bundle=bundle_path.exists(),
        cosign_ok=cosign_ok,
        sigstore_py_ok=sigstore_ok,
        payload_json_exists=payload_json_path.exists(),
        dsse_payload_b64_valid=dsse_payload_b64_valid,
        payload_digest_match=payload_digest_match,
        canonicalization_ok=canonicalization_ok,
        mismatch=mismatch,
        failures=failures,
        notes=notes,
    )


def write_outputs(verdicts: list[Verdict]) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mismatches = [dataclasses.asdict(v) for v in verdicts if v.mismatch]
    failures = [dataclasses.asdict(v) for v in verdicts if v.failures]

    payload = {
        "summary": {
            "vectors_scanned": len(verdicts),
            "vectors_with_failures": len(failures),
            "mismatch_count": len(mismatches),
        },
        "mismatches": mismatches,
        "failures": failures,
    }
    write(OUT_DIR / "mismatches.json", json.dumps(payload, indent=2).encode("utf-8"))

    with (OUT_DIR / "report.txt").open("w", encoding="utf-8") as handle:
        handle.write("DSSE ↔ JCS Conformance Report\n")
        handle.write(f"Vectors scanned: {len(verdicts)}\n")
        handle.write(f"Vectors with failures: {len(failures)}\n")
        handle.write(f"Mismatches: {len(mismatches)}\n\n")

        for v in verdicts:
            bundle_state = "bundle" if v.bundle else "no-bundle"
            handle.write(
                f"- {v.path} [{bundle_state}] "
                f"cosign={v.cosign_ok} sigstore.py={v.sigstore_py_ok} "
                f"canonical_ok={v.canonicalization_ok}\n"
            )
            for reason in v.failures:
                handle.write(f"    ! {reason}\n")
            for note in v.notes:
                handle.write(f"    i {note}\n")

    return len(mismatches) + len(failures)


def main() -> int:
    args = parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not ROOT.exists():
        msg = "test-vectors/ directory not found"
        payload = {
            "summary": {
                "vectors_scanned": 0,
                "vectors_with_failures": 1,
                "mismatch_count": 0,
            },
            "mismatches": [],
            "failures": [{"path": str(ROOT), "error": msg}],
        }
        write(OUT_DIR / "mismatches.json", json.dumps(payload, indent=2).encode("utf-8"))
        (OUT_DIR / "report.txt").write_text(
            "DSSE ↔ JCS Conformance Report\n"
            "Vectors scanned: 0\n"
            "Vectors with failures: 1\n"
            "Mismatches: 0\n"
            "\n"
            "! test-vectors/ directory not found\n",
            encoding="utf-8",
        )
        return 0 if args.allow_empty else 2

    vectors = sorted(ROOT.rglob("*.dsse"))
    if not vectors:
        payload = {
            "summary": {
                "vectors_scanned": 0,
                "vectors_with_failures": 1,
                "mismatch_count": 0,
            },
            "mismatches": [],
            "failures": [{"path": str(ROOT), "error": "no .dsse vectors found"}],
        }
        write(OUT_DIR / "mismatches.json", json.dumps(payload, indent=2).encode("utf-8"))
        (OUT_DIR / "report.txt").write_text(
            "DSSE ↔ JCS Conformance Report\n"
            "Vectors scanned: 0\n"
            "Vectors with failures: 1\n"
            "Mismatches: 0\n"
            "\n"
            "! no .dsse vectors found\n",
            encoding="utf-8",
        )
        return 0 if args.allow_empty else 2

    verdicts = [analyze_vector(path, args.cosign_timeout_seconds) for path in vectors]
    findings = write_outputs(verdicts)
    if findings:
        print(json.dumps({"finding_count": findings}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
