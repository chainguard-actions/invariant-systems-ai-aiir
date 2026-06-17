# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — generic commitment receipts for arbitrary artifacts.

"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aiir._core import (
    CLI_VERSION,
    _canonical_json,
    _now_rfc3339,
    _run_git,
    _sha256,
    _strip_terminal_escapes,
    _strip_url_credentials,
)


COMMITMENT_RECEIPT_TYPE = "aiir.commitment_receipt"
COMMITMENT_RECEIPT_SCHEMA_VERSION = "aiir/commitment_receipt.v1"
COMMITMENT_RECEIPT_ID_PREFIX = "c1-"
COMMITMENT_CORE_KEYS = frozenset(
    {
        "type",
        "schema",
        "version",
        "subject",
        "statement",
        "artifacts",
        "provenance",
    }
)

_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([.+\-][0-9a-zA-Z.+\-]*)?$")
_SHA256_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_VALID_ARTIFACT_TYPES = frozenset({"file", "directory", "digest"})


def is_commitment_receipt(receipt: Any) -> bool:
    """Return True when the object looks like an AIIR commitment receipt."""

    return (
        isinstance(receipt, dict)
        and receipt.get("type") == COMMITMENT_RECEIPT_TYPE
        and isinstance(receipt.get("schema"), str)
        and str(receipt.get("schema")) == COMMITMENT_RECEIPT_SCHEMA_VERSION
    )


def parse_commitment_digest_spec(spec: str) -> Dict[str, Any]:
    """Parse LABEL=sha256:<hex> into a normalized commitment artifact entry."""

    text = _strip_terminal_escapes(str(spec)).strip()
    label, sep, digest = text.partition("=")
    label = label.strip()
    digest = digest.strip().lower()
    if not sep or not label or not _SHA256_RE.match(digest):
        raise ValueError(
            "Invalid --commitment-digest. Use LABEL=sha256:<64 lowercase hex>."
        )
    return {
        "type": "digest",
        "ref": label[:200],
        "digest": digest,
        "role": "artifact",
    }


def build_commitment_path_artifact(
    path_like: str, cwd: Optional[str] = None
) -> Dict[str, Any]:
    """Build a normalized artifact entry for a file or directory path."""

    raw_path = _strip_terminal_escapes(str(path_like)).strip()
    if not raw_path:
        raise ValueError("Commitment artifact path cannot be empty.")

    base_dir = Path(cwd or os.getcwd()).resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    if candidate.is_symlink():
        raise ValueError(f"Commitment artifacts may not be symlinks: {raw_path}")

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"Commitment artifact not found: {raw_path}") from exc

    ref = _artifact_ref(resolved, base_dir)
    if resolved.is_file():
        return {
            "type": "file",
            "ref": ref,
            "digest": _sha256_file(resolved),
            "size": resolved.stat().st_size,
            "role": "artifact",
        }

    if resolved.is_dir():
        members = _directory_members(resolved)
        file_count = sum(1 for member in members if member.get("type") == "file")
        return {
            "type": "directory",
            "ref": ref,
            "digest": "sha256:" + _sha256(_canonical_json(members)),
            "entry_count": len(members),
            "file_count": file_count,
            "members": members,
            "role": "artifact",
        }

    raise ValueError(f"Commitment artifacts must be files or directories: {raw_path}")


def build_commitment_receipt(
    *,
    subject_name: str,
    summary: str,
    artifacts: Sequence[Dict[str, Any]],
    subject_kind: str = "artifact_commitment",
    cwd: Optional[str] = None,
    namespace: Optional[str] = None,
    generator: str = "aiir.cli",
) -> Dict[str, Any]:
    """Build a generic AIIR commitment receipt for arbitrary artifacts."""

    name = _clean_text(subject_name, field_name="subject name", limit=200)
    kind = _clean_text(subject_kind, field_name="subject kind", limit=80)
    summary_text = _clean_text(summary, field_name="commitment summary", limit=2000)

    normalized_artifacts = [_normalize_artifact(artifact) for artifact in artifacts]
    if not normalized_artifacts:
        raise ValueError(
            "Commitment receipts require at least one --commitment-artifact or --commitment-digest."
        )

    repo_url = _detect_repository_url(cwd)
    receipt_core: Dict[str, Any] = {
        "type": COMMITMENT_RECEIPT_TYPE,
        "schema": COMMITMENT_RECEIPT_SCHEMA_VERSION,
        "version": CLI_VERSION,
        "subject": {
            "name": name,
            "kind": kind,
        },
        "statement": {
            "summary": summary_text,
        },
        "artifacts": normalized_artifacts,
        "provenance": {
            **({"repository": repo_url} if repo_url else {}),
            "tool": f"https://github.com/invariant-systems-ai/aiir@{CLI_VERSION}",
            "generator": _clean_text(generator, field_name="generator", limit=120),
        },
    }

    core_json = _canonical_json(receipt_core)
    content_hash = "sha256:" + _sha256(core_json)
    receipt_id = f"{COMMITMENT_RECEIPT_ID_PREFIX}{_sha256(core_json)[:32]}"

    return {
        **receipt_core,
        "receipt_id": receipt_id,
        "content_hash": content_hash,
        "timestamp": _now_rfc3339(),
        "extensions": {
            **(
                {"namespace": _clean_text(namespace, field_name="namespace", limit=120)}
                if namespace
                else {}
            ),
        },
    }


def verify_commitment_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Verify a commitment receipt's content-addressed integrity."""

    errors: List[str] = []
    if receipt.get("type") != COMMITMENT_RECEIPT_TYPE:
        errors.append(f"unknown receipt type: {receipt.get('type')!r}")
    if receipt.get("schema") != COMMITMENT_RECEIPT_SCHEMA_VERSION:
        errors.append(f"unknown schema: {receipt.get('schema')!r}")

    version = receipt.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        errors.append(f"invalid version format: {version!r}")

    try:
        subject = _normalize_subject(receipt.get("subject"))
        statement = _normalize_statement(receipt.get("statement"))
        artifacts = _normalize_artifacts(receipt.get("artifacts"))
        provenance = _normalize_provenance(receipt.get("provenance"))
    except ValueError as exc:
        errors.append(str(exc))
        subject = {"name": "unknown", "kind": "unknown"}
        statement = {"summary": ""}
        artifacts = []
        provenance = {}

    if errors:
        return {
            "valid": False,
            "receipt_type": "commitment_receipt",
            "receipt_id": str(receipt.get("receipt_id", "")),
            "subject_name": subject.get("name", "unknown"),
            "subject_kind": subject.get("kind", "unknown"),
            "artifact_count": len(artifacts),
            "errors": errors,
        }

    receipt_core = {
        "type": COMMITMENT_RECEIPT_TYPE,
        "schema": COMMITMENT_RECEIPT_SCHEMA_VERSION,
        "version": version,
        "subject": subject,
        "statement": statement,
        "artifacts": artifacts,
        "provenance": provenance,
    }

    core_json = _canonical_json(receipt_core)
    expected_hash = "sha256:" + _sha256(core_json)
    expected_id = f"{COMMITMENT_RECEIPT_ID_PREFIX}{_sha256(core_json)[:32]}"
    stored_hash = str(receipt.get("content_hash", ""))
    stored_id = str(receipt.get("receipt_id", ""))

    hash_ok = hmac.compare_digest(
        stored_hash.encode("utf-8"), expected_hash.encode("utf-8")
    )
    id_ok = hmac.compare_digest(stored_id.encode("utf-8"), expected_id.encode("utf-8"))

    result: Dict[str, Any] = {
        "valid": hash_ok and id_ok,
        "receipt_type": "commitment_receipt",
        "receipt_id": stored_id,
        "content_hash_match": hash_ok,
        "receipt_id_match": id_ok,
        "subject_name": subject.get("name", "unknown"),
        "subject_kind": subject.get("kind", "unknown"),
        "artifact_count": len(artifacts),
        "errors": [],
    }
    if not hash_ok:
        result["errors"].append("content hash mismatch")
    if not id_ok:
        result["errors"].append("receipt_id mismatch")
    if result["valid"]:
        result["expected_content_hash"] = expected_hash
        result["expected_receipt_id"] = expected_id
    return result


def _clean_text(value: Optional[str], *, field_name: str, limit: int) -> str:
    text = _strip_terminal_escapes(str(value or "")).strip()
    if not text:
        raise ValueError(f"{field_name.capitalize()} cannot be empty.")
    return text[:limit]


def _normalize_subject(subject: Any) -> Dict[str, str]:
    if not isinstance(subject, dict):
        raise ValueError("commitment subject must be an object")
    return {
        "name": _clean_text(subject.get("name"), field_name="subject name", limit=200),
        "kind": _clean_text(subject.get("kind"), field_name="subject kind", limit=80),
    }


def _normalize_statement(statement: Any) -> Dict[str, str]:
    if not isinstance(statement, dict):
        raise ValueError("commitment statement must be an object")
    return {
        "summary": _clean_text(
            statement.get("summary"),
            field_name="commitment summary",
            limit=2000,
        )
    }


def _normalize_provenance(provenance: Any) -> Dict[str, Any]:
    if not isinstance(provenance, dict):
        raise ValueError("commitment provenance must be an object")
    tool = _clean_text(provenance.get("tool"), field_name="tool", limit=200)
    generator = _clean_text(
        provenance.get("generator"), field_name="generator", limit=120
    )
    normalized: Dict[str, Any] = {
        "tool": tool,
        "generator": generator,
    }
    repository = provenance.get("repository")
    if repository is not None:
        normalized["repository"] = _clean_text(
            repository, field_name="repository", limit=400
        )
    return normalized


def _normalize_artifacts(artifacts: Any) -> List[Dict[str, Any]]:
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("commitment artifacts must be a non-empty array")
    return [_normalize_artifact(artifact) for artifact in artifacts]


def _normalize_artifact(artifact: Any) -> Dict[str, Any]:
    if not isinstance(artifact, dict):
        raise ValueError("commitment artifact entries must be objects")

    artifact_type = _clean_text(
        artifact.get("type"), field_name="artifact type", limit=40
    )
    if artifact_type not in _VALID_ARTIFACT_TYPES:
        raise ValueError(f"unsupported commitment artifact type: {artifact_type!r}")

    digest = _clean_text(
        artifact.get("digest"), field_name="artifact digest", limit=80
    ).lower()
    if not _SHA256_RE.match(digest):
        raise ValueError(f"invalid artifact digest: {digest!r}")

    normalized: Dict[str, Any] = {
        "type": artifact_type,
        "ref": _clean_text(artifact.get("ref"), field_name="artifact ref", limit=400),
        "digest": digest,
        "role": _clean_text(
            artifact.get("role", "artifact"), field_name="artifact role", limit=40
        ),
    }

    if artifact_type == "file":
        size = artifact.get("size")
        if not isinstance(size, int) or size < 0:
            raise ValueError("file commitment artifacts require a non-negative size")
        normalized["size"] = size
        return normalized

    if artifact_type == "directory":
        entry_count = artifact.get("entry_count")
        file_count = artifact.get("file_count")
        if not isinstance(entry_count, int) or entry_count < 0:
            raise ValueError(
                "directory commitment artifacts require a non-negative entry_count"
            )
        if not isinstance(file_count, int) or file_count < 0:
            raise ValueError(
                "directory commitment artifacts require a non-negative file_count"
            )
        members = artifact.get("members")
        if not isinstance(members, list):
            raise ValueError("directory commitment artifacts require a members array")
        normalized_members: List[Dict[str, Any]] = []
        for member in members:
            normalized_members.append(_normalize_directory_member(member))
        normalized["entry_count"] = entry_count
        normalized["file_count"] = file_count
        normalized["members"] = normalized_members
    return normalized


def _normalize_directory_member(member: Any) -> Dict[str, Any]:
    if not isinstance(member, dict):
        raise ValueError("directory members must be objects")

    member_type = _clean_text(
        member.get("type"), field_name="directory member type", limit=20
    )
    if member_type not in {"file", "directory"}:
        raise ValueError(f"unsupported directory member type: {member_type!r}")

    normalized: Dict[str, Any] = {
        "path": _clean_text(
            member.get("path"), field_name="directory member path", limit=400
        ),
        "type": member_type,
    }
    if member_type == "file":
        digest = _clean_text(
            member.get("digest"), field_name="directory member digest", limit=80
        ).lower()
        if not _SHA256_RE.match(digest):
            raise ValueError(f"invalid directory member digest: {digest!r}")
        size = member.get("size")
        if not isinstance(size, int) or size < 0:
            raise ValueError("directory file members require a non-negative size")
        normalized["digest"] = digest
        normalized["size"] = size
    return normalized


def _detect_repository_url(cwd: Optional[str]) -> Optional[str]:
    try:
        repo_url = _run_git(["remote", "get-url", "origin"], cwd=cwd).strip() or None
    except RuntimeError:
        return None
    return _strip_url_credentials(repo_url) if repo_url else None


def _artifact_ref(resolved: Path, base_dir: Path) -> str:
    try:
        return resolved.relative_to(base_dir).as_posix()
    except ValueError:
        return resolved.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _directory_members(root: Path) -> List[Dict[str, Any]]:
    members: List[Dict[str, Any]] = []
    items = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    for item in items:
        if item.is_symlink():
            raise ValueError(f"Commitment directories may not contain symlinks: {item}")
        rel_path = item.relative_to(root).as_posix()
        if item.is_dir():
            members.append({"path": rel_path, "type": "directory"})
            continue
        if not item.is_file():
            raise ValueError(
                f"Unsupported directory member in commitment artifact: {item}"
            )
        members.append(
            {
                "path": rel_path,
                "type": "file",
                "digest": _sha256_file(item),
                "size": item.stat().st_size,
            }
        )
    return members
