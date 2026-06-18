# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — normalize receipts into a governance-ready evidence stream.

"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aiir._core import _now_rfc3339

EvidenceSource = Union[Dict[str, Any], List[Dict[str, Any]]]


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _as_receipt_list(source: EvidenceSource) -> List[Dict[str, Any]]:
    """Normalize supported inputs into a list of receipt dicts."""
    if isinstance(source, list):
        return [receipt for receipt in source if isinstance(receipt, dict)]

    if not isinstance(source, dict):
        return []

    receipts = source.get("receipts")
    if isinstance(receipts, list):
        return [receipt for receipt in receipts if isinstance(receipt, dict)]

    if source.get("receipt_id") and isinstance(source.get("commit"), dict):
        return [source]

    return []


def _artifact_key_candidates(receipt: Dict[str, Any]) -> List[str]:
    """Return keys that can identify receipt artifacts on disk."""
    commit = _as_dict(receipt.get("commit"))
    content_hash = str(receipt.get("content_hash") or "")
    return [
        str(receipt.get("receipt_id") or ""),
        str(commit.get("sha") or ""),
        content_hash,
    ]


def _build_receipt_artifact_index(
    receipts_dir: Optional[str],
) -> Dict[str, Dict[str, Any]]:
    """Build a best-effort index of JSON, CBOR, and Sigstore artifacts."""
    if not receipts_dir:
        return {}

    root = Path(receipts_dir).resolve()
    if not root.is_dir():
        return {}

    index: Dict[str, Dict[str, Any]] = {}
    for json_path in sorted(root.glob("*.json")):
        try:
            receipt = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(receipt, dict):
            continue

        artifact = {
            "json_path": str(json_path),
            "cbor_present": json_path.with_suffix(".cbor").is_file(),
            "sigstore_present": Path(str(json_path) + ".sigstore").is_file(),
            "artifact_source": "receipt-dir",
        }
        for key in _artifact_key_candidates(receipt):
            if key:
                index[key] = artifact
    return index


def _get_agent_attestation(receipt: Dict[str, Any]) -> Dict[str, Any]:
    candidate = _as_dict(receipt.get("extensions")).get("agent_attestation")
    return candidate if isinstance(candidate, dict) else {}


def _get_editor_provenance(receipt: Dict[str, Any]) -> Dict[str, Any]:
    candidate = _as_dict(receipt.get("extensions")).get("editor_provenance")
    return candidate if isinstance(candidate, dict) else {}


def _resolve_artifacts(
    receipt: Dict[str, Any],
    artifact_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve CBOR and Sigstore presence from embedded fields or receipt dir.

    ``sigstore_present`` reflects CLAIMED presence (embedded extension or
    on-disk sidecar file) and is used for display/evidence-tier only.
    It is NOT a verified-signature predicate; see ``_has_verified_sigstore_sidecar``
    in ``_verify_release.py`` for the ``require_signing`` gate (C5.1).
    """
    extensions = _as_dict(receipt.get("extensions"))
    embedded_sigstore = bool(
        extensions.get("sigstore") or extensions.get("sigstore_bundle")
    )
    resolved = {
        "cbor_present": False,
        # sigstore_claimed: embedded extension fields only (unverified, display use)
        "sigstore_claimed": embedded_sigstore,
        # sigstore_present: will be overridden below if artifact_index has a sidecar
        "sigstore_present": embedded_sigstore,
        "artifact_source": "embedded" if embedded_sigstore else "receipt-only",
    }

    for key in _artifact_key_candidates(receipt):
        artifact = artifact_index.get(key)
        if artifact:
            resolved.update(artifact)
            break
    return resolved


def get_receipt_evidence_tier(
    receipt: Dict[str, Any], *, sigstore_present: bool = False
) -> str:
    """Classify a receipt as signed, provable, heuristic, or unsigned."""
    editor = _get_editor_provenance(receipt)
    records = _as_list(editor.get("records"))
    agent = _get_agent_attestation(receipt)
    ai_attestation = _as_dict(receipt.get("ai_attestation"))
    ai_involved = bool(
        ai_attestation.get("is_ai_authored") or agent.get("tool_id") or records
    )

    if sigstore_present:
        return "signed"
    if records:
        return "provable"
    if ai_involved:
        return "heuristic"
    return "unsigned"


def normalize_receipt_to_evidence(
    receipt: Dict[str, Any],
    artifact_index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Convert one receipt into a flat, policy-friendly evidence event."""
    artifacts = _resolve_artifacts(receipt, artifact_index or {})
    commit = _as_dict(receipt.get("commit"))
    author = _as_dict(commit.get("author"))
    ai_attestation = _as_dict(receipt.get("ai_attestation"))
    agent = _get_agent_attestation(receipt)
    editor = _get_editor_provenance(receipt)
    records = [
        record for record in _as_list(editor.get("records")) if isinstance(record, dict)
    ]
    first_record = records[0] if records else {}
    files = [path for path in _as_list(commit.get("files")) if isinstance(path, str)]
    files_changed = commit.get("files_changed")
    attested_tool = str(editor.get("toolId") or agent.get("tool_id") or "")
    editor_model_parts = [
        first_record.get("modelVendor"),
        first_record.get("modelFamily"),
    ]
    editor_model = " ".join(str(part) for part in editor_model_parts if part)
    model = editor_model or str(agent.get("model_class") or "")
    attested_system = (
        f"{attested_tool} via {model}"
        if attested_tool and model
        else attested_tool or model or "No explicit tool attested"
    )
    tier = get_receipt_evidence_tier(
        receipt,
        sigstore_present=bool(artifacts.get("sigstore_present")),
    )

    return {
        "schema": "aiir/evidence_event.v1",
        "receipt_id": receipt.get("receipt_id"),
        "commit_sha": commit.get("sha"),
        "timestamp": receipt.get("timestamp"),
        "author_name": author.get("name"),
        "author_email": author.get("email"),
        "subject": commit.get("subject"),
        "files": files,
        "files_changed": files_changed
        if isinstance(files_changed, int)
        else len(files),
        "ai_authored": bool(ai_attestation.get("is_ai_authored")),
        "authorship_class": ai_attestation.get("authorship_class") or "human",
        "ai_signals": [
            str(item)
            for item in _as_list(ai_attestation.get("signals_detected"))
            if isinstance(item, str)
        ],
        "bot_signals": [
            str(item)
            for item in _as_list(ai_attestation.get("bot_signals_detected"))
            if isinstance(item, str)
        ],
        "agent_tool": agent.get("tool_id"),
        "editor_tool": editor.get("toolId"),
        "editor_mode": editor.get("mode"),
        "editor_record_count": len(records),
        "attested_system": attested_system,
        "cbor_present": bool(artifacts.get("cbor_present")),
        "sigstore_present": bool(artifacts.get("sigstore_present")),
        "artifact_source": artifacts.get("artifact_source"),
        "evidence_tier": tier,
        "upgrade_needed": (
            "none"
            if tier == "signed"
            else "sign-in-ci"
            if tier == "provable"
            else "add-provenance"
            if tier == "heuristic"
            else "add-provenance-and-sign"
        ),
        "release_proof_ready": tier == "signed",
    }


def import_evidence_stream(
    source: EvidenceSource,
    receipts_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Import receipts into a normalized evidence stream for downstream systems."""
    receipts = _as_receipt_list(source)
    artifact_index = _build_receipt_artifact_index(receipts_dir)
    source_format = source.get("format") if isinstance(source, dict) else "receipts"
    events = [
        normalize_receipt_to_evidence(receipt, artifact_index) for receipt in receipts
    ]
    return {
        "format": "aiir.evidence_stream.v1",
        "source_format": source_format,
        "imported_at": _now_rfc3339(),
        "events": events,
    }


def summarize_evidence_stream(stream: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate evidence events into governance-friendly outputs."""
    events = [
        event for event in _as_list(stream.get("events")) if isinstance(event, dict)
    ]
    tier_counts = {"signed": 0, "provable": 0, "heuristic": 0, "unsigned": 0}
    trend: Dict[str, Dict[str, Any]] = {}
    hot_paths: Dict[str, Dict[str, Any]] = {}
    systems: Dict[str, int] = {}
    ai_receipts = 0
    heuristic_only = 0
    provable_unsigned = 0
    unsigned_ai = 0
    signed_ready = 0

    for event in events:
        tier = str(event.get("evidence_tier") or "unsigned")
        if tier not in tier_counts:
            tier = "unsigned"
        tier_counts[tier] += 1

        timestamp = str(event.get("timestamp") or "")
        day = (
            timestamp.split("T", 1)[0] if "T" in timestamp else (timestamp or "unknown")
        )
        day_stats = trend.setdefault(
            day,
            {
                "date": day,
                "total": 0,
                "ai_receipts": 0,
                "signed": 0,
                "provable": 0,
                "heuristic": 0,
                "unsigned": 0,
            },
        )
        day_stats["total"] += 1
        day_stats[tier] += 1

        ai_involved = bool(
            event.get("ai_authored")
            or event.get("agent_tool")
            or event.get("editor_tool")
            or event.get("ai_signals")
        )
        if ai_involved:
            ai_receipts += 1
            day_stats["ai_receipts"] += 1
            if tier == "heuristic":
                heuristic_only += 1
            if tier == "provable":
                provable_unsigned += 1
            if not event.get("sigstore_present"):
                unsigned_ai += 1
            for file_path in _as_list(event.get("files")):
                if not isinstance(file_path, str) or not file_path:
                    continue
                path_stats = hot_paths.setdefault(
                    file_path,
                    {
                        "path": file_path,
                        "count": 0,
                        "signed": 0,
                        "provable": 0,
                        "heuristic": 0,
                        "unsigned": 0,
                        "latest_commit": None,
                    },
                )
                path_stats["count"] += 1
                path_stats[tier] += 1
                path_stats["latest_commit"] = event.get("commit_sha")

            system = str(event.get("attested_system") or "")
            if system and system != "No explicit tool attested":
                systems[system] = systems.get(system, 0) + 1

        if event.get("release_proof_ready"):
            signed_ready += 1

    trend_rows = sorted(trend.values(), key=lambda item: item["date"])
    for row in trend_rows:
        total = row["total"]
        row["ai_percentage"] = (
            round((row["ai_receipts"] / total) * 100, 1) if total else 0.0
        )

    total = len(events)
    ready_ratio = round((signed_ready / total) * 100, 1) if total else 0.0
    hot_path_rows = sorted(
        hot_paths.values(),
        key=lambda item: (-item["count"], str(item["path"])),
    )[:10]
    top_systems = [
        {"system": system, "count": count}
        for system, count in sorted(
            systems.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    return {
        "format": "aiir.evidence_summary.v1",
        "generated_at": _now_rfc3339(),
        "total_receipts": total,
        "ai_receipts": ai_receipts,
        "evidence_tiers": tier_counts,
        "ai_coverage_trend": trend_rows,
        "unsigned_risk": {
            "ai_receipts_without_signing": unsigned_ai,
            "heuristic_only": heuristic_only,
            "provable_but_unsigned": provable_unsigned,
        },
        "hot_path_ai_changes": hot_path_rows,
        "top_ai_systems": top_systems,
        "release_proof_readiness": {
            "ready_receipts": signed_ready,
            "needs_signing": total - signed_ready,
            "ready_ratio": ready_ratio,
            "status": "ready"
            if total and signed_ready == total
            else "partial"
            if signed_ready
            else "unsigned",
        },
    }
