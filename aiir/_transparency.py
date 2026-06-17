# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Offline Rekor checkpoint and witness verification helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aiir._core import MAX_RECEIPT_FILE_SIZE
from aiir._ed25519 import verify as _ed25519_verify


_RE_UINT = re.compile(r"^(0|[1-9][0-9]*)$")
_RE_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_RE_KEY_ID = re.compile(r"^[0-9a-f]{8}$")
_RE_KEY_NAME = re.compile(r"^[^\s+]+$")

_MAX_SIGNATURES = 16
_NOTE_SIGNATURE_PREFIX = "\u2014 "
_NOTE_TYPE_ED25519 = 0x01
_NOTE_TYPE_COSIGNATURE = 0x04


def parse_witness_quorum(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(0|[1-9][0-9]*)-of-(0|[1-9][0-9]*)", value.strip())
    if match is None:
        raise ValueError("witness policy must look like N-of-M")
    required = int(match.group(1))
    total = int(match.group(2))
    if required > total:
        raise ValueError("witness policy cannot require more witnesses than it allows")
    return required, total


def validate_trust_root_schema(document: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(document, dict):
        return ["Trust root must be a JSON object"]

    if document.get("schema") != "aiir.trust.v1":
        errors.append("schema must be 'aiir.trust.v1'")

    logs = document.get("logs")
    if not isinstance(logs, list):
        errors.append("logs must be an array")
    else:
        for index, entry in enumerate(logs):
            prefix = f"logs[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{prefix} must be an object")
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not _RE_KEY_NAME.match(name):
                errors.append(f"{prefix}.name must be a non-empty key name")
            key_id = entry.get("checkpoint_key_id")
            if key_id is not None and (
                not isinstance(key_id, str) or not _RE_KEY_ID.match(key_id)
            ):
                errors.append(
                    f"{prefix}.checkpoint_key_id must be 8 lowercase hex chars"
                )
            log_id = entry.get("log_id")
            if log_id is not None and not isinstance(log_id, str):
                errors.append(f"{prefix}.log_id must be a string when present")
            if entry.get("public_key_type") != "ed25519":
                errors.append(f"{prefix}.public_key_type must be 'ed25519'")
            public_key_b64 = entry.get("public_key_b64")
            try:
                _decode_public_key(public_key_b64, prefix)
            except ValueError as exc:
                errors.append(str(exc))

    witnesses = document.get("witnesses")
    if witnesses is not None and not isinstance(witnesses, list):
        errors.append("witnesses must be an array when present")
    elif isinstance(witnesses, list):
        for index, entry in enumerate(witnesses):
            prefix = f"witnesses[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{prefix} must be an object")
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not _RE_KEY_NAME.match(name):
                errors.append(f"{prefix}.name must be a non-empty key name")
            key_id = entry.get("key_id")
            if key_id is not None and (
                not isinstance(key_id, str) or not _RE_KEY_ID.match(key_id)
            ):
                errors.append(f"{prefix}.key_id must be 8 lowercase hex chars")
            if entry.get("public_key_type") != "ed25519":
                errors.append(f"{prefix}.public_key_type must be 'ed25519'")
            public_key_b64 = entry.get("public_key_b64")
            try:
                _decode_public_key(public_key_b64, prefix)
            except ValueError as exc:
                errors.append(str(exc))
            min_version = entry.get("min_version")
            if min_version is not None and (
                not isinstance(min_version, int) or min_version < 1
            ):
                errors.append(f"{prefix}.min_version must be a positive integer")

    policy = document.get("policy")
    if policy is not None and not isinstance(policy, dict):
        errors.append("policy must be an object when present")
    elif isinstance(policy, dict):
        skew = policy.get("max_future_skew_seconds")
        if skew is not None and (not isinstance(skew, int) or skew < 0):
            errors.append(
                "policy.max_future_skew_seconds must be a non-negative integer"
            )
        require_witnesses = policy.get("require_witnesses")
        if require_witnesses is not None and not isinstance(require_witnesses, dict):
            errors.append("policy.require_witnesses must be an object when present")
        elif isinstance(require_witnesses, dict):
            for key, value in require_witnesses.items():
                if not isinstance(key, str):
                    errors.append("policy.require_witnesses keys must be strings")
                    continue
                if not isinstance(value, str):
                    errors.append(f"policy.require_witnesses.{key} must be a string")
                    continue
                try:
                    parse_witness_quorum(value)
                except ValueError as exc:
                    errors.append(f"policy.require_witnesses.{key}: {exc}")

    return errors


def validate_rekor_bundle_schema(document: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(document, dict):
        return ["Rekor bundle must be a JSON object"]

    if document.get("schema") != "aiir.rekor.bundle.v1":
        errors.append("schema must be 'aiir.rekor.bundle.v1'")

    log_id = document.get("log_id")
    if not isinstance(log_id, str) or not log_id:
        errors.append("log_id is required")

    artifact_sha256 = document.get("artifact_sha256")
    if not isinstance(artifact_sha256, str) or not _RE_HASH.match(artifact_sha256):
        errors.append("artifact_sha256 must match 'sha256:' + 64 lowercase hex chars")

    body_b64 = document.get("body_b64")
    if not isinstance(body_b64, str) or not body_b64:
        errors.append("body_b64 is required")
    else:
        try:
            base64.b64decode(body_b64, validate=True)
        except (ValueError, TypeError):
            errors.append("body_b64 must be valid base64")

    body_hash = document.get("body_hash")
    if body_hash is not None and (
        not isinstance(body_hash, str) or not _RE_HASH.match(body_hash)
    ):
        errors.append("body_hash must match 'sha256:' + 64 lowercase hex chars")

    for key in ("log_index", "integrated_time"):
        if not _is_uint_value(document.get(key)):
            errors.append(f"{key} must be a non-negative integer or decimal string")

    inclusion = document.get("inclusion_proof")
    if not isinstance(inclusion, dict):
        errors.append("inclusion_proof must be an object")
    else:
        for key in ("tree_size",):
            if not _is_uint_value(inclusion.get(key)):
                errors.append(
                    f"inclusion_proof.{key} must be a non-negative integer or decimal string"
                )
        root_hash = inclusion.get("root_hash")
        try:
            _decode_hash_b64(root_hash, "inclusion_proof.root_hash")
        except ValueError as exc:
            errors.append(str(exc))
        hashes = inclusion.get("hashes")
        if not isinstance(hashes, list):
            errors.append("inclusion_proof.hashes must be an array")
        else:
            for index, value in enumerate(hashes):
                try:
                    _decode_hash_b64(value, f"inclusion_proof.hashes[{index}]")
                except ValueError as exc:
                    errors.append(str(exc))
                    break
        checkpoint = inclusion.get("checkpoint")
        if not isinstance(checkpoint, str) or not checkpoint:
            errors.append("inclusion_proof.checkpoint must be a non-empty signed note")

    consistency = document.get("consistency_proof")
    if consistency is not None:
        if not isinstance(consistency, dict):
            errors.append("consistency_proof must be an object when present")
        else:
            for key in ("old_tree_size", "new_tree_size"):
                if not _is_uint_value(consistency.get(key)):
                    errors.append(
                        f"consistency_proof.{key} must be a non-negative integer or decimal string"
                    )
            hashes = consistency.get("hashes")
            if not isinstance(hashes, list):
                errors.append("consistency_proof.hashes must be an array")
            else:
                for index, value in enumerate(hashes):
                    try:
                        _decode_hash_b64(value, f"consistency_proof.hashes[{index}]")
                    except ValueError as exc:
                        errors.append(str(exc))
                        break

    return errors


def verify_transparency_material(
    artifact_path: str,
    rekor_bundle_path: str,
    trust_root_path: str,
    *,
    witnessed_checkpoint_path: Optional[str] = None,
    require_witnesses: Optional[str] = None,
) -> Dict[str, Any]:
    errors: List[str] = []

    try:
        artifact_bytes = _read_bytes(artifact_path, "Artifact")
        trust_root = _load_json(trust_root_path, "Trust root")
        bundle_doc = _load_json(rekor_bundle_path, "Rekor bundle")
    except (FileNotFoundError, ValueError) as exc:
        return {"valid": False, "error": str(exc), "errors": [str(exc)]}

    trust_errors = validate_trust_root_schema(trust_root)
    if trust_errors:
        return {"valid": False, "error": trust_errors[0], "errors": trust_errors}

    try:
        canonical_bundle = _canonicalize_bundle(bundle_doc, artifact_bytes)
    except ValueError as exc:
        return {"valid": False, "error": str(exc), "errors": [str(exc)]}

    trust = _parse_trust_root(trust_root)
    policy_string = _resolve_witness_policy(trust_root, require_witnesses)
    required_witnesses, total_witnesses = parse_witness_quorum(policy_string)

    artifact_sha256 = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    artifact_hash_match = hmac.compare_digest(
        artifact_sha256.encode("ascii"),
        canonical_bundle["artifact_sha256"].encode("ascii"),
    )
    if not artifact_hash_match:
        errors.append("artifact hash does not match Rekor bundle")

    computed_body_hash = (
        "sha256:" + hashlib.sha256(canonical_bundle["body_bytes"]).hexdigest()
    )
    body_hash_match = True
    if canonical_bundle.get("body_hash"):
        body_hash_match = hmac.compare_digest(
            computed_body_hash.encode("ascii"),
            str(canonical_bundle["body_hash"]).encode("ascii"),
        )
        if not body_hash_match:
            errors.append("body_hash does not match body_b64")

    checkpoint_result = _verify_checkpoint_note(
        canonical_bundle["checkpoint_note"],
        trust["logs"],
        expected_log_id=canonical_bundle.get("log_id"),
    )
    errors.extend(checkpoint_result.get("errors", []))

    inclusion_verified = False
    if checkpoint_result.get("valid"):
        proof_root_match = hmac.compare_digest(
            canonical_bundle["proof_root_hash"],
            checkpoint_result["checkpoint"]["root_hash_bytes"],
        )
        if not proof_root_match:
            errors.append(
                "inclusion proof root hash does not match the signed checkpoint"
            )
        if (
            canonical_bundle["tree_size"]
            != checkpoint_result["checkpoint"]["tree_size"]
        ):
            errors.append(
                "inclusion proof tree size does not match the signed checkpoint"
            )
        inclusion_verified = verify_inclusion_proof(
            _hash_leaf(canonical_bundle["body_bytes"]),
            canonical_bundle["log_index"],
            canonical_bundle["tree_size"],
            canonical_bundle["proof_hashes"],
            checkpoint_result["checkpoint"]["root_hash_bytes"],
        )
        if not inclusion_verified:
            errors.append(
                "inclusion proof did not reconstruct the checkpoint root hash"
            )

    witness_result: Dict[str, Any] = {
        "provided": witnessed_checkpoint_path is not None,
        "required": policy_string,
        "verified_witnesses": [],
        "trusted_witnesses": len(trust["witnesses"]),
        "valid": required_witnesses == 0,
        "body_match": None,
        "consistency_proof_verified": None,
        "errors": [],
    }

    if witnessed_checkpoint_path is not None:
        try:
            witness_note = _read_text(witnessed_checkpoint_path, "Witnessed checkpoint")
            witness_result = _verify_witnessed_checkpoint(
                witness_note,
                trust,
                checkpoint_result.get("checkpoint"),
                canonical_bundle.get("consistency_proof"),
                required_witnesses=required_witnesses,
                total_witnesses=total_witnesses,
            )
        except (FileNotFoundError, ValueError) as exc:
            witness_result = {
                "provided": True,
                "required": policy_string,
                "verified_witnesses": [],
                "trusted_witnesses": len(trust["witnesses"]),
                "valid": False,
                "body_match": None,
                "consistency_proof_verified": None,
                "errors": [str(exc)],
            }
        errors.extend(witness_result.get("errors", []))
    elif required_witnesses > 0:
        witness_result["valid"] = False
        witness_result["errors"] = ["witnessed checkpoint is required by policy"]
        errors.extend(witness_result["errors"])

    valid = (
        not errors and artifact_hash_match and body_hash_match and inclusion_verified
    )
    valid = (
        valid
        and bool(checkpoint_result.get("valid"))
        and bool(witness_result.get("valid"))
    )

    result: Dict[str, Any] = {
        "valid": valid,
        "artifact_sha256": artifact_sha256,
        "artifact_hash_match": artifact_hash_match,
        "body_hash_match": body_hash_match,
        "rekor_bundle": {
            "schema": canonical_bundle.get("schema"),
            "log_id": canonical_bundle.get("log_id"),
            "log_index": canonical_bundle.get("log_index"),
            "integrated_time": canonical_bundle.get("integrated_time"),
            "integrated_time_rfc3339": _format_timestamp(
                canonical_bundle.get("integrated_time")
            ),
            "inclusion_proof_verified": inclusion_verified,
            "checkpoint": {
                "origin": checkpoint_result.get("checkpoint", {}).get("origin"),
                "tree_size": checkpoint_result.get("checkpoint", {}).get("tree_size"),
                "root_hash": checkpoint_result.get("checkpoint", {}).get("root_hash"),
                "log_signature_verified": checkpoint_result.get("valid", False),
                "checkpoint_key_id": checkpoint_result.get("checkpoint_key_id"),
            },
        },
        "witnessed_checkpoint": witness_result,
        "errors": errors,
    }
    if errors:
        result["error"] = errors[0]
    return result


def verify_inclusion_proof(
    leaf_hash: bytes,
    log_index: int,
    tree_size: int,
    hashes: Sequence[bytes],
    expected_root_hash: bytes,
) -> bool:
    if tree_size < 1 or log_index < 0 or log_index >= tree_size:
        return False
    computed = leaf_hash
    fn = log_index
    sn = tree_size - 1
    proof_index = 0
    while sn > 0:
        if proof_index >= len(hashes):
            return False
        sibling = hashes[proof_index]
        proof_index += 1
        if fn % 2 == 1 or fn == sn:
            computed = _hash_node(sibling, computed)
            while fn != 0 and fn % 2 == 0:
                fn //= 2
                sn //= 2
        else:
            computed = _hash_node(computed, sibling)
        fn //= 2
        sn //= 2
    if proof_index != len(hashes):
        return False
    return hmac.compare_digest(computed, expected_root_hash)


def verify_consistency_proof(
    old_tree_size: int,
    new_tree_size: int,
    old_root_hash: bytes,
    new_root_hash: bytes,
    hashes: Sequence[bytes],
) -> bool:
    if old_tree_size < 1 or old_tree_size > new_tree_size:
        return False
    if old_tree_size == new_tree_size:
        return not hashes and hmac.compare_digest(old_root_hash, new_root_hash)
    if not hashes:
        return False

    fn = old_tree_size - 1
    sn = new_tree_size - 1
    while fn % 2 == 1:
        fn //= 2
        sn //= 2

    if fn == 0:
        fr = old_root_hash
        sr = old_root_hash
        proof_index = 0
    else:
        fr = hashes[0]
        sr = hashes[0]
        proof_index = 1
    while proof_index < len(hashes):
        sibling = hashes[proof_index]
        proof_index += 1
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            fr = _hash_node(sibling, fr)
            sr = _hash_node(sibling, sr)
            while fn != 0 and fn % 2 == 0:
                fn //= 2
                sn //= 2
        else:
            sr = _hash_node(sr, sibling)
        fn //= 2
        sn //= 2

    return (
        sn == 0
        and hmac.compare_digest(fr, old_root_hash)
        and hmac.compare_digest(sr, new_root_hash)
    )


def _verify_witnessed_checkpoint(
    note_text: str,
    trust: Dict[str, Any],
    inclusion_checkpoint: Optional[Dict[str, Any]],
    consistency_proof: Optional[Dict[str, Any]],
    *,
    required_witnesses: int,
    total_witnesses: int,
) -> Dict[str, Any]:
    errors: List[str] = []
    witness_note = _parse_signed_note(note_text)
    witness_checkpoint = _parse_checkpoint_body(witness_note["body"])
    log_result = _verify_checkpoint_note(note_text, trust["logs"])
    errors.extend(log_result.get("errors", []))

    body_match: Optional[bool] = None
    consistency_verified: Optional[bool] = None
    if inclusion_checkpoint is not None:
        body_match = hmac.compare_digest(
            witness_note["body_bytes"], inclusion_checkpoint["body_bytes"]
        )
        if body_match:
            consistency_verified = True
        elif consistency_proof is None:
            consistency_verified = False
            errors.append(
                "consistency proof is required when the witnessed checkpoint differs"
            )
        else:
            consistency_verified = verify_consistency_proof(
                consistency_proof["old_tree_size"],
                consistency_proof["new_tree_size"],
                inclusion_checkpoint["root_hash_bytes"],
                witness_checkpoint["root_hash_bytes"],
                consistency_proof["hashes"],
            )
            if not consistency_verified:
                errors.append(
                    "consistency proof did not connect the bundled checkpoint to the witnessed checkpoint"
                )

    max_future_skew = trust.get("max_future_skew_seconds", 300)
    current_time = int(time.time())
    verified_witnesses: List[Dict[str, Any]] = []
    for witness in trust["witnesses"]:
        expected_key_id = witness["key_id"]
        matching = [
            signature
            for signature in witness_note["signatures"]
            if signature["name"] == witness["name"]
            and signature["key_id_hex"] == expected_key_id
        ]
        for signature in matching:
            if signature["signature_type"] != _NOTE_TYPE_COSIGNATURE:
                errors.append(
                    f"witness {witness['name']} used the wrong signature type"
                )
                continue
            timestamp = int.from_bytes(signature["signature_bytes"][:8], "big")
            if timestamp > current_time + max_future_skew:
                errors.append(
                    f"witness {witness['name']} timestamp is too far in the future"
                )
                continue
            message = (
                b"cosignature/v1\n"
                + f"time {timestamp}\n".encode("ascii")
                + witness_note["body_bytes"]
            )
            if not _ed25519_verify(
                witness["public_key"],
                message,
                signature["signature_bytes"][8:],
            ):
                errors.append(f"witness {witness['name']} signature did not verify")
                continue
            verified_witnesses.append(
                {
                    "name": witness["name"],
                    "key_id": witness["key_id"],
                    "timestamp": timestamp,
                    "timestamp_rfc3339": _format_timestamp(timestamp),
                    "trusted": True,
                }
            )
            break

    if len(trust["witnesses"]) < total_witnesses:
        errors.append(
            "trust root does not define enough witnesses for the requested policy"
        )

    valid = (
        not errors
        and bool(log_result.get("valid"))
        and (required_witnesses == 0 or len(verified_witnesses) >= required_witnesses)
    )
    if required_witnesses > 0 and len(verified_witnesses) < required_witnesses:
        errors.append("witness policy was not satisfied")
        valid = False

    return {
        "provided": True,
        "required": f"{required_witnesses}-of-{total_witnesses}",
        "verified_witnesses": verified_witnesses,
        "trusted_witnesses": len(trust["witnesses"]),
        "valid": valid,
        "body_match": body_match,
        "consistency_proof_verified": consistency_verified,
        "checkpoint": {
            "origin": witness_checkpoint["origin"],
            "tree_size": witness_checkpoint["tree_size"],
            "root_hash": witness_checkpoint["root_hash"],
            "log_signature_verified": log_result.get("valid", False),
            "checkpoint_key_id": log_result.get("checkpoint_key_id"),
        },
        "errors": errors,
    }


def _verify_checkpoint_note(
    note_text: str,
    trusted_logs: Sequence[Dict[str, Any]],
    *,
    expected_log_id: Optional[str] = None,
) -> Dict[str, Any]:
    errors: List[str] = []
    note = _parse_signed_note(note_text)
    checkpoint = _parse_checkpoint_body(note["body"])

    trusted_log = _select_log(checkpoint["origin"], trusted_logs, expected_log_id)
    if trusted_log is None:
        errors.append(
            f"no trusted log matches checkpoint origin {checkpoint['origin']!r}"
        )
        return {"valid": False, "errors": errors}

    verified = False
    for signature in note["signatures"]:
        if signature["name"] != trusted_log["name"]:
            continue
        if signature["key_id_hex"] != trusted_log["checkpoint_key_id"]:
            continue
        if signature["signature_type"] != _NOTE_TYPE_ED25519:
            errors.append("checkpoint used an unexpected signature type")
            continue
        if not _ed25519_verify(
            trusted_log["public_key"],
            note["body_bytes"],
            signature["signature_bytes"],
        ):
            errors.append("checkpoint signature did not verify")
            continue
        verified = True
        break

    if not verified:
        errors.append("no trusted checkpoint signature verified")

    if checkpoint["log_id"] is not None and expected_log_id is not None:
        if not hmac.compare_digest(
            str(expected_log_id).encode("utf-8"),
            str(trusted_log.get("log_id") or expected_log_id).encode("utf-8"),
        ):
            errors.append("checkpoint log_id did not match the trusted log")

    return {
        "valid": not errors,
        "checkpoint": checkpoint,
        "checkpoint_key_id": trusted_log["checkpoint_key_id"],
        "errors": errors,
    }


def _canonicalize_bundle(
    document: Dict[str, Any], artifact_bytes: bytes
) -> Dict[str, Any]:
    if document.get("mediaType") == "application/vnd.dev.sigstore.bundle.v0.3+json":
        return _parse_sigstore_bundle(document, artifact_bytes)

    errors = validate_rekor_bundle_schema(document)
    if errors:
        raise ValueError(errors[0])

    inclusion = document["inclusion_proof"]
    return {
        "schema": document.get("schema"),
        "log_id": str(document.get("log_id") or ""),
        "artifact_sha256": str(document.get("artifact_sha256") or ""),
        "body_hash": document.get("body_hash"),
        "body_bytes": base64.b64decode(str(document["body_b64"]), validate=True),
        "log_index": _parse_uint(document["log_index"]),
        "integrated_time": _parse_uint(document["integrated_time"]),
        "tree_size": _parse_uint(inclusion["tree_size"]),
        "proof_root_hash": _decode_hash_b64(
            inclusion["root_hash"], "inclusion_proof.root_hash"
        ),
        "proof_hashes": [
            _decode_hash_b64(value, "inclusion_proof.hash")
            for value in inclusion["hashes"]
        ],
        "checkpoint_note": str(inclusion["checkpoint"]),
        "consistency_proof": _parse_consistency_proof(
            document.get("consistency_proof")
        ),
    }


def _parse_sigstore_bundle(
    document: Dict[str, Any], artifact_bytes: bytes
) -> Dict[str, Any]:
    message_signature = document.get("messageSignature")
    if not isinstance(message_signature, dict):
        raise ValueError("Sigstore bundle is missing messageSignature")

    message_digest = message_signature.get("messageDigest")
    if not isinstance(message_digest, dict):
        raise ValueError("Sigstore bundle is missing messageDigest")
    if message_digest.get("algorithm") != "SHA2_256":
        raise ValueError("Sigstore bundle must use SHA2_256")

    digest_b64 = message_digest.get("digest")
    if not isinstance(digest_b64, str):
        raise ValueError("Sigstore bundle digest must be a string")
    computed_b64 = base64.b64encode(hashlib.sha256(artifact_bytes).digest()).decode(
        "ascii"
    )
    if not hmac.compare_digest(
        digest_b64.encode("ascii"), computed_b64.encode("ascii")
    ):
        raise ValueError("Sigstore bundle digest does not match the artifact")

    verification_material = document.get("verificationMaterial")
    if not isinstance(verification_material, dict):
        raise ValueError("Sigstore bundle is missing verificationMaterial")
    tlog_entries = verification_material.get("tlogEntries")
    if not isinstance(tlog_entries, list) or not tlog_entries:
        raise ValueError("Sigstore bundle is missing Rekor tlog entries")

    entry = tlog_entries[0]
    if not isinstance(entry, dict):
        raise ValueError("Sigstore bundle tlog entry is not an object")
    canonicalized_body = entry.get("canonicalizedBody")
    if not isinstance(canonicalized_body, str) or not canonicalized_body:
        raise ValueError("Sigstore bundle is missing canonicalizedBody")
    try:
        body_bytes = base64.b64decode(canonicalized_body, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Sigstore bundle canonicalizedBody is invalid: {exc}"
        ) from exc

    try:
        rekor_body = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Sigstore bundle canonicalizedBody is invalid JSON: {exc}"
        ) from exc

    rekor_hash = ((rekor_body.get("spec") or {}).get("data") or {}).get("hash") or {}
    if rekor_hash.get("algorithm") != "sha256":
        raise ValueError("Sigstore bundle Rekor body must use sha256")

    artifact_sha256 = "sha256:" + hashlib.sha256(artifact_bytes).hexdigest()
    rekor_sha256 = "sha256:" + str(rekor_hash.get("value") or "")
    if not hmac.compare_digest(
        artifact_sha256.encode("ascii"), rekor_sha256.encode("ascii")
    ):
        raise ValueError("Sigstore bundle Rekor body hash does not match the artifact")

    inclusion = entry.get("inclusionProof")
    if not isinstance(inclusion, dict):
        raise ValueError("Sigstore bundle is missing inclusionProof")
    checkpoint = inclusion.get("checkpoint")
    checkpoint_note = (
        checkpoint.get("envelope") if isinstance(checkpoint, dict) else None
    )
    if not isinstance(checkpoint_note, str) or not checkpoint_note:
        raise ValueError("Sigstore bundle is missing checkpoint.envelope")

    log_id_block = entry.get("logId")
    log_id = (
        str(log_id_block.get("keyId") or "") if isinstance(log_id_block, dict) else ""
    )
    return {
        "schema": "sigstore.bundle.v0.3",
        "log_id": log_id,
        "artifact_sha256": artifact_sha256,
        "body_hash": "sha256:" + hashlib.sha256(body_bytes).hexdigest(),
        "body_bytes": body_bytes,
        "log_index": _parse_uint(inclusion.get("logIndex")),
        "integrated_time": _parse_uint(entry.get("integratedTime")),
        "tree_size": _parse_uint(inclusion.get("treeSize")),
        "proof_root_hash": _decode_hash_b64(
            inclusion.get("rootHash"), "inclusionProof.rootHash"
        ),
        "proof_hashes": [
            _decode_hash_b64(value, "inclusionProof.hash")
            for value in inclusion.get("hashes") or []
        ],
        "checkpoint_note": checkpoint_note,
        "consistency_proof": None,
    }


def _parse_trust_root(document: Dict[str, Any]) -> Dict[str, Any]:
    logs = []
    for entry in document.get("logs") or []:
        public_key = _decode_public_key(entry.get("public_key_b64"), "logs")
        checkpoint_key_id = entry.get("checkpoint_key_id")
        if checkpoint_key_id is None:
            checkpoint_key_id = _note_key_id(
                entry["name"], _NOTE_TYPE_ED25519, public_key
            )
        logs.append(
            {
                "name": entry["name"],
                "log_id": entry.get("log_id"),
                "checkpoint_key_id": str(checkpoint_key_id),
                "public_key": public_key,
            }
        )

    witnesses = []
    for entry in document.get("witnesses") or []:
        public_key = _decode_public_key(entry.get("public_key_b64"), "witnesses")
        key_id = entry.get("key_id")
        if key_id is None:
            key_id = _note_key_id(entry["name"], _NOTE_TYPE_COSIGNATURE, public_key)
        witnesses.append(
            {
                "name": entry["name"],
                "key_id": str(key_id),
                "public_key": public_key,
                "min_version": int(entry.get("min_version") or 1),
            }
        )

    policy = document.get("policy") or {}
    return {
        "logs": logs,
        "witnesses": witnesses,
        "max_future_skew_seconds": int(policy.get("max_future_skew_seconds") or 300),
    }


def _resolve_witness_policy(document: Dict[str, Any], override: Optional[str]) -> str:
    if override is not None:
        try:
            parse_witness_quorum(override)
            return override
        except ValueError:
            pass

        policies = (document.get("policy") or {}).get("require_witnesses") or {}
        resolved = policies.get(override)
        if not isinstance(resolved, str):
            raise ValueError(f"unknown witness policy: {override}")
        parse_witness_quorum(resolved)
        return resolved

    policies = (document.get("policy") or {}).get("require_witnesses") or {}
    default_policy = policies.get("default", "0-of-0")
    if not isinstance(default_policy, str):
        raise ValueError("default witness policy must be a string")
    parse_witness_quorum(default_policy)
    return default_policy


def _parse_signed_note(note_text: str) -> Dict[str, Any]:
    if not isinstance(note_text, str):
        raise ValueError("signed note must be text")
    # Signed notes are LF-canonical, but Windows text files may round-trip them as
    # CRLF. Normalize CRLF back to LF before validating and verifying signatures.
    note_text = note_text.replace("\r\n", "\n")
    if any(ord(char) < 0x20 and char != "\n" for char in note_text):
        raise ValueError("signed note contains control characters")
    if not note_text.endswith("\n"):
        raise ValueError("signed note must end with a newline")

    separator = note_text.rfind("\n\n")
    if separator == -1:
        raise ValueError("signed note is missing the separator before signatures")

    body = note_text[: separator + 1]
    signature_block = note_text[separator + 2 :]
    signature_lines = [line for line in signature_block.splitlines() if line]
    if not signature_lines:
        raise ValueError("signed note must contain at least one signature line")
    if len(signature_lines) > _MAX_SIGNATURES:
        raise ValueError("signed note has too many signatures")

    signatures: List[Dict[str, Any]] = []
    for line in signature_lines:
        if not line.startswith(_NOTE_SIGNATURE_PREFIX):
            raise ValueError("signed note contains a malformed signature line")
        try:
            name, encoded = line[len(_NOTE_SIGNATURE_PREFIX) :].split(" ", 1)
        except ValueError as exc:
            raise ValueError("signed note contains a malformed signature line") from exc
        if not _RE_KEY_NAME.match(name):
            raise ValueError("signed note contains an invalid key name")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"signed note contains invalid base64: {exc}") from exc
        if len(raw) < 4:
            raise ValueError("signed note signature payload is too short")
        signature_bytes = raw[4:]
        if len(signature_bytes) == 64:
            signature_type = _NOTE_TYPE_ED25519
        elif len(signature_bytes) == 72:
            signature_type = _NOTE_TYPE_COSIGNATURE
        else:
            signature_type = -1
        signatures.append(
            {
                "name": name,
                "key_id_hex": raw[:4].hex(),
                "signature_bytes": signature_bytes,
                "signature_type": signature_type,
            }
        )

    return {
        "body": body,
        "body_bytes": body.encode("utf-8"),
        "signatures": signatures,
    }


def _parse_checkpoint_body(body: str) -> Dict[str, Any]:
    if not body.endswith("\n"):
        raise ValueError("checkpoint body must end with a newline")
    lines = body[:-1].split("\n")
    if len(lines) < 3:
        raise ValueError(
            "checkpoint body must contain origin, tree size, and root hash"
        )
    if not lines[0]:
        raise ValueError("checkpoint origin must be non-empty")
    if not _RE_UINT.match(lines[1]):
        raise ValueError("checkpoint tree size must be decimal with no leading zeroes")
    root_hash_bytes = _decode_hash_b64(lines[2], "checkpoint root hash")
    if any(not line for line in lines[3:]):
        raise ValueError("checkpoint extension lines must be non-empty")
    return {
        "origin": lines[0],
        "tree_size": int(lines[1]),
        "root_hash": lines[2],
        "root_hash_bytes": root_hash_bytes,
        "extensions": lines[3:],
        "body": body,
        "body_bytes": body.encode("utf-8"),
        "log_id": None,
    }


def _read_bytes(path_text: str, label: str) -> bytes:
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path_text}")
    if path.is_symlink():
        raise ValueError(f"{label} is a symlink (refusing to read): {path_text}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Cannot stat {label.lower()}: {exc}") from exc
    if size > MAX_RECEIPT_FILE_SIZE:
        raise ValueError(f"{label} is too large ({size} bytes)")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read {label.lower()}: {exc}") from exc


def _read_text(path_text: str, label: str) -> str:
    try:
        return _read_bytes(path_text, label).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not valid UTF-8") from exc


def _load_json(path_text: str, label: str) -> Dict[str, Any]:
    text = _read_text(path_text, label)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"{label} must be a JSON object")
    return document


def _parse_consistency_proof(document: Any) -> Optional[Dict[str, Any]]:
    if document is None:
        return None
    if not isinstance(document, dict):
        raise ValueError("consistency_proof must be an object")
    return {
        "old_tree_size": _parse_uint(document.get("old_tree_size")),
        "new_tree_size": _parse_uint(document.get("new_tree_size")),
        "hashes": [
            _decode_hash_b64(value, "consistency hash")
            for value in document.get("hashes") or []
        ],
    }


def _parse_uint(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean values are not valid integers")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("integers must be non-negative")
        return value
    if isinstance(value, str) and _RE_UINT.match(value):
        return int(value)
    raise ValueError("value must be a non-negative integer or decimal string")


def _is_uint_value(value: Any) -> bool:
    try:
        _parse_uint(value)
        return True
    except ValueError:
        return False


def _decode_hash_b64(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty base64 string")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be valid base64") from exc
    if len(decoded) != 32:
        raise ValueError(f"{label} must decode to 32 bytes")
    return decoded


def _decode_public_key(value: Any, prefix: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{prefix}.public_key_b64 must be a non-empty base64 string")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{prefix}.public_key_b64 must be valid base64") from exc
    if len(decoded) != 32:
        raise ValueError(f"{prefix}.public_key_b64 must decode to 32 bytes")
    return decoded


def _note_key_id(name: str, signature_type: int, public_key: bytes) -> str:
    digest = hashlib.sha256(
        name.encode("utf-8") + b"\n" + bytes([signature_type]) + public_key
    ).digest()
    return digest[:4].hex()


def _select_log(
    origin: str,
    trusted_logs: Sequence[Dict[str, Any]],
    expected_log_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    for entry in trusted_logs:
        if entry["name"] != origin:
            continue
        if expected_log_id is not None and entry.get("log_id") not in (
            None,
            expected_log_id,
        ):
            continue
        return entry
    return None


def _hash_leaf(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def _hash_node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _format_timestamp(value: Any) -> Optional[str]:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return None
