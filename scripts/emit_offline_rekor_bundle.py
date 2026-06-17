#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from aiir._sign import validate_sigstore_bundle
from aiir._transparency import validate_rekor_bundle_schema


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return document


def _require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def build_rekor_bundle(
    artifact_path: Path,
    bundle: dict[str, Any],
    *,
    consistency_proof: dict[str, Any] | None = None,
    log_id_override: str | None = None,
) -> dict[str, Any]:
    artifact_bytes = artifact_path.read_bytes()
    errors = validate_sigstore_bundle(artifact_bytes, bundle)
    if errors:
        raise ValueError(errors[0])

    verification_material = _require_dict(
        bundle.get("verificationMaterial"),
        "verificationMaterial",
    )
    tlog_entries = _require_list(
        verification_material.get("tlogEntries"),
        "verificationMaterial.tlogEntries",
    )
    if not tlog_entries:
        raise ValueError("verificationMaterial.tlogEntries must not be empty")
    entry = _require_dict(tlog_entries[0], "verificationMaterial.tlogEntries[0]")
    inclusion = _require_dict(
        entry.get("inclusionProof"),
        "tlogEntries[0].inclusionProof",
    )
    checkpoint = _require_dict(
        inclusion.get("checkpoint"),
        "tlogEntries[0].inclusionProof.checkpoint",
    )
    log_id_block = _require_dict(entry.get("logId"), "tlogEntries[0].logId")
    body_b64 = _require_string(
        entry.get("canonicalizedBody"),
        "tlogEntries[0].canonicalizedBody",
    )
    try:
        body_bytes = base64.b64decode(body_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"tlogEntries[0].canonicalizedBody is not valid base64: {exc}"
        ) from exc

    rekor_bundle = {
        "schema": "aiir.rekor.bundle.v1",
        "log_id": log_id_override
        or _require_string(log_id_block.get("keyId"), "tlogEntries[0].logId.keyId"),
        "artifact_sha256": f"sha256:{sha256_file(artifact_path)}",
        "body_b64": body_b64,
        "body_hash": f"sha256:{hashlib.sha256(body_bytes).hexdigest()}",
        "log_index": inclusion.get("logIndex", entry.get("logIndex")),
        "integrated_time": entry.get("integratedTime"),
        "inclusion_proof": {
            "tree_size": inclusion.get("treeSize"),
            "root_hash": inclusion.get("rootHash"),
            "hashes": inclusion.get("hashes"),
            "checkpoint": _require_string(
                checkpoint.get("envelope"),
                "tlogEntries[0].inclusionProof.checkpoint.envelope",
            ),
        },
    }
    if consistency_proof is not None:
        rekor_bundle["consistency_proof"] = consistency_proof

    schema_errors = validate_rekor_bundle_schema(rekor_bundle)
    if schema_errors:
        raise ValueError(schema_errors[0])
    return rekor_bundle


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit an aiir.rekor.bundle.v1 document from a Sigstore bundle.",
    )
    parser.add_argument("--artifact", required=True, help="Path to the signed artifact")
    parser.add_argument(
        "--bundle", required=True, help="Path to the Sigstore bundle JSON"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the emitted aiir.rekor.bundle.v1 JSON",
    )
    parser.add_argument(
        "--consistency-proof",
        default="",
        help="Optional JSON file with old_tree_size, new_tree_size, and hashes[]",
    )
    parser.add_argument(
        "--log-id-override",
        default="",
        help="Optional log_id value to use instead of tlogEntries[0].logId.keyId",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifact_path = Path(args.artifact)
    bundle_path = Path(args.bundle)
    output_path = Path(args.output)

    if not artifact_path.is_file():
        raise SystemExit(f"artifact not found: {artifact_path}")
    if not bundle_path.is_file():
        raise SystemExit(f"bundle not found: {bundle_path}")

    bundle = load_json(bundle_path)
    consistency_proof = None
    if args.consistency_proof:
        consistency_proof = load_json(Path(args.consistency_proof))

    try:
        rekor_bundle = build_rekor_bundle(
            artifact_path,
            bundle,
            consistency_proof=consistency_proof,
            log_id_override=args.log_id_override or None,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(rekor_bundle, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
