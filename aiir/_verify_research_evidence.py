# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""AIIR internal — research-evidence receipt verification (verify-only)."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any, Dict, List, cast

from aiir._core import MAX_RECEIPT_FILE_SIZE, MAX_RECEIPTS_PER_RANGE, _check_json_depth

CONTRACT_VERSION = "aiir/research_evidence_receipt.v0.1"
CANONICALIZATION = "aiir-canon-0"
VALID_DISCLOSURE_TIERS = frozenset({"public", "internal", "restricted", "embargoed"})
VALID_STATUSES = frozenset(
    {
        "hypothesis",
        "computational_evidence",
        "proof_sketch",
        "verified",
        "published",
        "disputed",
        "retracted",
    }
)
_RE_RECORD_ID = re.compile(r"^r1-[0-9a-f]{32}\Z")
_RE_CONTENT_HASH = re.compile(r"^sha256:[0-9a-f]{64}\Z")


def is_research_evidence_receipt(data: Any) -> bool:
    """Return True when *data* looks like a research-evidence receipt."""
    return isinstance(data, dict) and data.get("contract_version") == CONTRACT_VERSION


def _canonical_research_evidence_bytes(
    timestamp: str,
    subject: Dict[str, Any],
    claim: Dict[str, Any],
    evidence: Dict[str, Any],
    governance: Dict[str, Any],
    proof: Dict[str, Any],
) -> bytes:
    payload = {
        "contract_version": CONTRACT_VERSION,
        "timestamp": timestamp,
        "subject": subject,
        "claim": claim,
        "evidence": evidence,
        "governance": governance,
        "proof": {
            "canonicalization": proof.get("canonicalization"),
        },
    }
    _check_json_depth(payload, max_depth=64)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _compute_research_evidence_hash(
    timestamp: str,
    subject: Dict[str, Any],
    claim: Dict[str, Any],
    evidence: Dict[str, Any],
    governance: Dict[str, Any],
    proof: Dict[str, Any],
) -> str:
    return hashlib.sha256(
        _canonical_research_evidence_bytes(
            timestamp,
            subject,
            claim,
            evidence,
            governance,
            proof,
        )
    ).hexdigest()


def _validate_artifact_list(
    artifacts: Any,
    field_name: str,
    errors: List[str],
) -> None:
    if not isinstance(artifacts, list):
        errors.append(f"{field_name} must be a list")
        return
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"{field_name}[{index}] must be an object")
            return
        for required_key in ("type", "ref", "digest"):
            if not isinstance(artifact.get(required_key), str) or not artifact.get(
                required_key
            ):
                errors.append(
                    f"{field_name}[{index}].{required_key} must be a non-empty string"
                )
                return


def verify_research_evidence_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a research-evidence receipt's content-addressed integrity."""
    result: Dict[str, Any] = {
        "valid": False,
        "errors": [],
        "receipt_type": "research_evidence_receipt",
    }

    if not isinstance(receipt, dict):
        result["errors"].append("receipt is not a dict")
        return result

    if receipt.get("contract_version") != CONTRACT_VERSION:
        result["errors"].append(f"contract_version must be {CONTRACT_VERSION!r}")
        return result

    timestamp = receipt.get("timestamp")
    subject = receipt.get("subject")
    claim = receipt.get("claim")
    evidence = receipt.get("evidence")
    governance = receipt.get("governance")
    proof = receipt.get("proof")
    record_id = receipt.get("record_id")

    if not isinstance(timestamp, str) or not timestamp:
        result["errors"].append("missing or invalid timestamp")
    if not isinstance(subject, dict):
        result["errors"].append("missing or invalid subject")
    if not isinstance(claim, dict):
        result["errors"].append("missing or invalid claim")
    if not isinstance(evidence, dict):
        result["errors"].append("missing or invalid evidence")
    if not isinstance(governance, dict):
        result["errors"].append("missing or invalid governance")
    if not isinstance(proof, dict):
        result["errors"].append("missing or invalid proof")
    if not isinstance(record_id, str) or not _RE_RECORD_ID.match(record_id):
        result["errors"].append("missing or invalid record_id")
    if result["errors"]:
        return result

    timestamp_value = cast(str, timestamp)
    subject_value = cast(Dict[str, Any], subject)
    claim_value = cast(Dict[str, Any], claim)
    evidence_value = cast(Dict[str, Any], evidence)
    governance_value = cast(Dict[str, Any], governance)
    proof_value = cast(Dict[str, Any], proof)

    required_subject_keys = ("kind", "repo", "program_id", "claim_id", "title")
    for key in required_subject_keys:
        if not isinstance(subject_value.get(key), str) or not subject_value.get(key):
            result["errors"].append(f"subject.{key} must be a non-empty string")

    if subject_value.get("kind") != "research_claim":
        result["errors"].append("subject.kind must be 'research_claim'")

    if (
        not isinstance(claim_value.get("status"), str)
        or claim_value.get("status") not in VALID_STATUSES
    ):
        result["errors"].append(f"claim.status must be one of {sorted(VALID_STATUSES)}")
    if not isinstance(claim_value.get("summary"), str) or not claim_value.get(
        "summary"
    ):
        result["errors"].append("claim.summary must be a non-empty string")
    non_claims = claim_value.get("non_claims")
    if not isinstance(non_claims, list) or any(
        not isinstance(item, str) for item in non_claims
    ):
        result["errors"].append("claim.non_claims must be a list of strings")
    if not isinstance(claim_value.get("last_reviewed"), str) or not claim_value.get(
        "last_reviewed"
    ):
        result["errors"].append("claim.last_reviewed must be a non-empty string")

    _validate_artifact_list(
        evidence_value.get("artifacts"), "evidence.artifacts", result["errors"]
    )
    _validate_artifact_list(
        evidence_value.get("verifiers"), "evidence.verifiers", result["errors"]
    )

    if not isinstance(governance_value.get("public_safe"), bool):
        result["errors"].append("governance.public_safe must be a boolean")
    if not isinstance(governance_value.get("ip_sensitive"), bool):
        result["errors"].append("governance.ip_sensitive must be a boolean")
    if governance_value.get("disclosure_tier") not in VALID_DISCLOSURE_TIERS:
        result["errors"].append(
            f"governance.disclosure_tier must be one of {sorted(VALID_DISCLOSURE_TIERS)}"
        )
    if not isinstance(
        governance_value.get("next_gate"), str
    ) or not governance_value.get("next_gate"):
        result["errors"].append("governance.next_gate must be a non-empty string")

    if proof_value.get("canonicalization") != CANONICALIZATION:
        result["errors"].append(f"proof.canonicalization must be {CANONICALIZATION!r}")

    stored_hash = proof_value.get("content_hash")
    if not isinstance(stored_hash, str) or not _RE_CONTENT_HASH.match(stored_hash):
        result["errors"].append(
            "proof.content_hash must be 'sha256:' plus 64 hex chars"
        )

    if result["errors"]:
        return result

    record_id_value = cast(str, record_id)
    stored_hash_value = cast(str, stored_hash)

    try:
        expected_hash = _compute_research_evidence_hash(
            timestamp_value,
            subject_value,
            claim_value,
            evidence_value,
            governance_value,
            proof_value,
        )
    except (RecursionError, ValueError):
        result["errors"].append("receipt structure too deeply nested")
        return result
    expected_content_hash = f"sha256:{expected_hash}"
    expected_record_id = f"r1-{expected_hash[:32]}"

    result["valid"] = hmac.compare_digest(
        stored_hash_value, expected_content_hash
    ) and hmac.compare_digest(
        record_id_value,
        expected_record_id,
    )
    result["claim_id"] = subject_value.get("claim_id")
    result["program_id"] = subject_value.get("program_id")
    result["disclosure_tier"] = governance_value.get("disclosure_tier")
    result["public_safe"] = governance_value.get("public_safe")
    result["content_hash_match"] = hmac.compare_digest(
        stored_hash_value, expected_content_hash
    )
    result["record_id_match"] = hmac.compare_digest(record_id_value, expected_record_id)

    if not result["content_hash_match"]:
        result["errors"].append("content hash mismatch")
    if not result["record_id_match"]:
        result["errors"].append("record_id mismatch")
    return result


def verify_research_evidence_receipt_set(
    receipts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify a list of research-evidence receipts."""
    if len(receipts) > MAX_RECEIPTS_PER_RANGE:
        return {
            "valid": False,
            "receipt_type": "research_evidence_receipt",
            "errors": [
                f"receipt array too large ({len(receipts)} items, max {MAX_RECEIPTS_PER_RANGE})"
            ],
        }

    results = [verify_research_evidence_receipt(receipt) for receipt in receipts]
    errors: List[str] = []
    for index, result in enumerate(results):
        if result.get("valid"):
            continue
        for error in result.get("errors", []):
            errors.append(f"receipt[{index}]: {error}")
    return {
        "valid": all(result.get("valid") for result in results),
        "receipt_type": "research_evidence_receipt",
        "receipts": results,
        "total": len(results),
        "valid_receipts": sum(1 for result in results if result.get("valid")),
        "errors": errors,
    }


def verify_research_evidence_receipt_file(filepath: str) -> Dict[str, Any]:
    """Load and verify a research-evidence receipt JSON file."""
    path = Path(filepath)
    if not path.exists():
        return {
            "valid": False,
            "errors": [f"File not found: {filepath}"],
            "receipt_type": "research_evidence_receipt",
        }
    if path.is_symlink():
        return {
            "valid": False,
            "errors": ["refusing to verify symlink"],
            "receipt_type": "research_evidence_receipt",
        }

    try:
        file_size = path.stat().st_size
    except OSError as error:
        return {
            "valid": False,
            "errors": [f"cannot stat file: {error}"],
            "receipt_type": "research_evidence_receipt",
        }
    if file_size > MAX_RECEIPT_FILE_SIZE:
        return {
            "valid": False,
            "errors": [f"file too large ({file_size} bytes)"],
            "receipt_type": "research_evidence_receipt",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return {
            "valid": False,
            "errors": [f"invalid JSON: {error}"],
            "receipt_type": "research_evidence_receipt",
        }

    if (
        isinstance(data, dict)
        and "receipts" in data
        and isinstance(data["receipts"], list)
    ):
        data = data["receipts"]

    if isinstance(data, dict):
        return verify_research_evidence_receipt(data)
    if isinstance(data, list):
        return verify_research_evidence_receipt_set(data)
    return {
        "valid": False,
        "errors": ["expected JSON object or array"],
        "receipt_type": "research_evidence_receipt",
    }
