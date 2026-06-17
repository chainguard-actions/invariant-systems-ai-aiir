# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""AIIR internal — editor provenance queue helpers.

Consumes the repo-local `.aiir/editor_provenance.jsonl` queue produced by editor
integrations and converts eligible records into receipt-side extension payloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aiir._core import _canonical_json, _sha256


def _hash_record(record: Dict[str, Any]) -> str:
    payload = {k: v for k, v in record.items() if k != "contentHash"}
    return "sha256:" + _sha256(_canonical_json(payload))


def _load_queue_records(queue_path: Path) -> List[Dict[str, Any]]:
    if not queue_path.exists():
        return []
    raw = queue_path.read_text(encoding="utf-8")
    records: List[Dict[str, Any]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("editor provenance queue contains a non-object record")
        records.append(parsed)
    return records


def _validate_queue_records(records: List[Dict[str, Any]]) -> None:
    previous_hash: Optional[str] = None
    for index, record in enumerate(records):
        content_hash = record.get("contentHash")
        if not isinstance(content_hash, str) or not content_hash:
            raise ValueError(
                f"editor provenance record {index + 1} is missing contentHash"
            )
        expected_hash = _hash_record(record)
        if content_hash != expected_hash:
            raise ValueError(
                f"editor provenance record {index + 1} failed content-hash validation"
            )
        previous = record.get("previousRecordHash")
        if previous_hash is None:
            if previous not in (None, ""):
                raise ValueError(
                    "editor provenance queue has a broken hash chain at the first record"
                )
        elif previous != previous_hash:
            raise ValueError(
                f"editor provenance queue has a broken hash chain at record {index + 1}"
            )
        previous_hash = content_hash


def _rechain_queue_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rebuilt: List[Dict[str, Any]] = []
    previous_hash: Optional[str] = None
    for record in records:
        next_record = dict(record)
        next_record["previousRecordHash"] = previous_hash
        next_record["contentHash"] = _hash_record(next_record)
        rebuilt.append(next_record)
        previous_hash = next_record["contentHash"]
    return rebuilt


def _repair_orphaned_queue_head(
    records: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    if len(records) < 2:
        return None

    first_previous = records[0].get("previousRecordHash")
    if not isinstance(first_previous, str) or not first_previous:
        return None

    for index, record in enumerate(records):
        content_hash = record.get("contentHash")
        if not isinstance(content_hash, str) or not content_hash:
            return None
        if content_hash != _hash_record(record):
            return None
        if index > 0 and record.get("previousRecordHash") != records[index - 1].get(
            "contentHash"
        ):
            return None

    return _rechain_queue_records(records)


def _merkle_root(leaves: List[str]) -> str:
    if not leaves:
        return "sha256:" + _sha256("")

    layer = list(leaves)
    while len(layer) > 1:
        next_layer: List[str] = []
        for index in range(0, len(layer), 2):
            left = layer[index]
            right = layer[index + 1] if index + 1 < len(layer) else left
            next_layer.append("sha256:" + _sha256(left + right))
        layer = next_layer
    return layer[0]


def _build_receipt_record(record: Dict[str, Any]) -> Dict[str, Any]:
    files = record.get("files", [])
    if not isinstance(files, list):
        raise ValueError("editor provenance record files must be a list")
    receipt_files: List[Dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("editor provenance record file entry must be an object")
        path = item.get("path")
        before_hash = item.get("beforeHash")
        after_hash = item.get("afterHash")
        if (
            not isinstance(path, str)
            or not isinstance(before_hash, str)
            or not isinstance(after_hash, str)
        ):
            raise ValueError(
                "editor provenance record file entry is missing required fields"
            )
        receipt_files.append(
            {
                "path": path,
                "beforeHash": before_hash,
                "afterHash": after_hash,
            }
        )
    return {
        "id": str(record.get("id", "")),
        "command": str(record.get("command", "generate")),
        **(
            {"source": str(record.get("source"))}
            if isinstance(record.get("source"), str) and record.get("source")
            else {}
        ),
        **(
            {"promptKind": str(record.get("promptKind"))}
            if isinstance(record.get("promptKind"), str) and record.get("promptKind")
            else {}
        ),
        **(
            {"createdAt": str(record.get("createdAt"))}
            if isinstance(record.get("createdAt"), str) and record.get("createdAt")
            else {}
        ),
        **(
            {"sessionId": str(record.get("sessionId"))}
            if isinstance(record.get("sessionId"), str) and record.get("sessionId")
            else {}
        ),
        **(
            {"branch": str(record.get("branch"))}
            if isinstance(record.get("branch"), str) and record.get("branch")
            else {}
        ),
        **(
            {"baseCommitSha": str(record.get("baseCommitSha"))}
            if isinstance(record.get("baseCommitSha"), str)
            and record.get("baseCommitSha")
            else {}
        ),
        **(
            {"modelVendor": str(record.get("modelVendor"))}
            if isinstance(record.get("modelVendor"), str) and record.get("modelVendor")
            else {}
        ),
        **(
            {"modelFamily": str(record.get("modelFamily"))}
            if isinstance(record.get("modelFamily"), str) and record.get("modelFamily")
            else {}
        ),
        **(
            {"previousRecordHash": str(record.get("previousRecordHash"))}
            if isinstance(record.get("previousRecordHash"), str)
            and record.get("previousRecordHash")
            else {}
        ),
        **(
            {"contentHash": str(record.get("contentHash"))}
            if isinstance(record.get("contentHash"), str) and record.get("contentHash")
            else {}
        ),
        "files": receipt_files,
    }


def _build_receipt_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": "aiir/editor_provenance.v1",
        "mode": "provable",
        "toolId": "aiir-vscode",
        "recordCount": 1,
        "chainHead": str(record.get("contentHash", "")),
        "merkleRoot": _merkle_root([str(record.get("contentHash", ""))]),
        "records": [_build_receipt_record(record)],
    }


def _build_receipt_payload_from_records(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    content_hashes = [
        str(record.get("contentHash", ""))
        for record in records
        if isinstance(record.get("contentHash"), str) and record.get("contentHash")
    ]
    return {
        "schema": "aiir/editor_provenance.v1",
        "mode": "provable",
        "toolId": "aiir-vscode",
        "recordCount": len(records),
        "chainHead": content_hashes[-1] if content_hashes else "",
        "merkleRoot": _merkle_root(content_hashes),
        "records": [_build_receipt_record(record) for record in records],
    }


def consume_editor_provenance(
    queue_path: str,
    current_head_sha: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Consume one eligible editor provenance record.

    Returns ``(payload, changed)`` where ``payload`` is the receipt-side
    ``extensions.editor_provenance`` object or ``None`` when no eligible record
    should be consumed. ``changed`` indicates whether the queue file was compacted.
    """

    path = Path(queue_path)
    records = _load_queue_records(path)
    if not records:
        return None, False

    try:
        _validate_queue_records(records)
    except ValueError as exc:
        repaired = None
        if (
            str(exc)
            == "editor provenance queue has a broken hash chain at the first record"
        ):
            repaired = _repair_orphaned_queue_head(records)
        if repaired is None:
            raise
        records = repaired
        path.write_text(
            "\n".join(
                json.dumps(item, separators=(",", ":"), ensure_ascii=False)
                for item in records
            )
            + "\n",
            encoding="utf-8",
        )

    active = [record for record in records if not record.get("consumed")]
    if len(active) == 0:
        return None, False

    eligible = []
    for record in active:
        base_commit_sha = record.get("baseCommitSha")
        if (
            isinstance(base_commit_sha, str)
            and base_commit_sha
            and current_head_sha == base_commit_sha
        ):
            continue
        eligible.append(record)

    if len(eligible) == 0:
        return None, False

    payload = _build_receipt_payload_from_records(eligible)
    remaining = [
        item for item in records if item not in eligible and not item.get("consumed")
    ]
    remaining = _rechain_queue_records(remaining)
    path.write_text(
        ""
        if not remaining
        else "\n".join(
            json.dumps(item, separators=(",", ":"), ensure_ascii=False)
            for item in remaining
        )
        + "\n",
        encoding="utf-8",
    )
    return payload, True
