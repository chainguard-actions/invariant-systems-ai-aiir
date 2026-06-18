# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — append-only JSONL receipt ledger with auto-index.

"""

from __future__ import annotations

import json
import os
import platform
import secrets
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aiir._core import (
    CONFIG_FILE,
    INDEX_FILE,
    LEDGER_DIR,
    LEDGER_FILE,
    _HAS_FCHMOD,
    _canonical_json,
    _now_rfc3339,
)
from aiir._agent_receipt import is_agent_receipt
from aiir._evidence import import_evidence_stream, summarize_evidence_stream

# ---------------------------------------------------------------------------
# Platform-level advisory file locking (fcntl on POSIX, msvcrt on Windows)
# ---------------------------------------------------------------------------

_IS_POSIX = platform.system() != "Windows"
if _IS_POSIX:
    import fcntl as _fcntl
else:  # pragma: no cover
    import msvcrt as _msvcrt

# Lock file name within the ledger directory
_LOCK_FILE = ".lock"

# O_NOFOLLOW makes os.open fail (ELOOP) if the final path component is a
# symlink, so an attacker who pre-places a symlink at .aiir/.lock / *.tmp /
# receipts.jsonl cannot redirect our writes to clobber an arbitrary file.
# Falls back to 0 on platforms without it (e.g. Windows).
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class _LedgerLock:
    """Advisory exclusive lock around ledger append+index operations.

    Uses fcntl.flock on POSIX and msvcrt.locking on Windows so concurrent
    runs cannot corrupt receipts.jsonl or index.json.
    """

    def __init__(self, ledger_dir: Path) -> None:
        self._path = ledger_dir / _LOCK_FILE
        self._fd: Optional[int] = None

    def __enter__(self) -> "_LedgerLock":
        self._fd = os.open(
            str(self._path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW, 0o600
        )
        if _IS_POSIX:
            _fcntl.flock(self._fd, _fcntl.LOCK_EX)
        else:  # pragma: no cover
            _msvcrt.locking(self._fd, _msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        return self

    def __exit__(self, *_: object) -> None:
        if self._fd is not None:
            if _IS_POSIX:
                _fcntl.flock(self._fd, _fcntl.LOCK_UN)
            else:  # pragma: no cover
                _msvcrt.locking(self._fd, _msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            os.close(self._fd)
            self._fd = None


def _ledger_paths(
    ledger_dir: Optional[str] = None,
) -> Tuple[Path, Path, Path]:
    """Return (dir, ledger_path, index_path) for the ledger."""
    base = Path(ledger_dir or LEDGER_DIR).resolve()
    return base, base / LEDGER_FILE, base / INDEX_FILE


def _config_path(config_dir: Optional[str] = None) -> Path:
    """Return the path to the config file."""
    return Path(config_dir or LEDGER_DIR).resolve() / CONFIG_FILE


def _is_valid_redaction_salt(value: object) -> bool:
    """Return True when value is a well-formed 64-hex-character redaction salt."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdefABCDEF" for c in value)
    )


def _ensure_redaction_salt(
    config: Dict[str, Any], cfg_path: Optional[Path] = None
) -> str:
    """Return a valid 64-hex redaction_salt from config, generating one if absent/malformed.

    When a new salt is generated it is persisted back into *config* and, if
    *cfg_path* is provided, written to disk via :func:`_save_config`.  This
    mirrors the idempotent backfill pattern used for ``instance_id``.

    The salt MUST NOT be emitted by export_ledger — only instance_id/namespace
    are exported (verified by the regression test in tests/test_audit_integrations.py).
    """
    if _is_valid_redaction_salt(config.get("redaction_salt")):
        return str(config["redaction_salt"])
    # Generate a fresh 256-bit random salt.
    salt = secrets.token_hex(32)
    config["redaction_salt"] = salt
    if cfg_path is not None:
        _save_config(cfg_path, config)
    return salt


def _load_config(config_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load .aiir/config.json, creating it with a fresh instance_id if absent.

    Also performs an idempotent backfill of ``redaction_salt`` (C6): if the
    loaded config is missing or has a malformed salt, a fresh one is generated
    and persisted, identical to the ``instance_id`` backfill pattern.
    """
    dir_path = Path(config_dir or LEDGER_DIR).resolve()
    cfg_path = dir_path / CONFIG_FILE
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("instance_id"), str):
                # Backfill redaction_salt if absent or malformed (idempotent).
                if not _is_valid_redaction_salt(data.get("redaction_salt")):
                    _ensure_redaction_salt(data, cfg_path)
                return data
        except (json.JSONDecodeError, OSError):  # pragma: no cover
            pass
    # Generate a new config with a stable instance_id and redaction_salt.
    config: Dict[str, Any] = {
        "instance_id": str(uuid.uuid4()),
        "created": _now_rfc3339(),
    }
    # _ensure_redaction_salt will generate and embed the salt; persist after.
    _ensure_redaction_salt(config)
    dir_path.mkdir(parents=True, exist_ok=True)
    _save_config(cfg_path, config)
    return config


def _save_config(cfg_path: Path, config: Dict[str, Any]) -> None:
    """Atomically write the config file."""
    tmp = cfg_path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW, 0o600)
    if _HAS_FCHMOD:
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp), str(cfg_path))


def _load_index(index_path: Path) -> Dict[str, Any]:
    """Load the ledger index, or return a fresh skeleton."""
    skeleton: Dict[str, Any] = {
        "version": 1,
        "receipt_count": 0,
        "ai_commit_count": 0,
        "bot_commit_count": 0,
        "signed_receipt_count": 0,
        "unsigned_receipt_count": 0,
        "ai_percentage": 0.0,
        "first_receipt": None,
        "latest_timestamp": None,
        "unique_authors": 0,
        "commits": {},
    }
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version") == 1:
                merged = {**skeleton, **data}
                if not isinstance(merged.get("commits"), dict):
                    merged["commits"] = {}
                if _needs_signing_backfill(data, merged):
                    _backfill_signing_metadata(
                        merged,
                        index_path.parent / LEDGER_FILE,
                    )
                return merged
        except (json.JSONDecodeError, OSError):  # pragma: no cover
            pass
    return skeleton


def _needs_signing_backfill(
    raw_index: Dict[str, Any], merged_index: Dict[str, Any]
) -> bool:
    """Return True when signed/unsigned aggregates need to be rebuilt from the ledger."""
    if int(merged_index.get("receipt_count", 0) or 0) == 0:
        return False
    if (
        "signed_receipt_count" not in raw_index
        or "unsigned_receipt_count" not in raw_index
    ):
        return True
    commits = merged_index.get("commits", {})
    return any(
        isinstance(entry, dict) and "signed" not in entry for entry in commits.values()
    )


def _is_structurally_valid_sigstore_bundle_dict(bundle: object) -> bool:
    """Return True when *bundle* is a dict with a valid Sigstore bundle shape.

    This is a self-contained shape check (no import from _verify_release) that
    requires:
      - mediaType starting with 'application/vnd.dev.sigstore.bundle'
      - verificationMaterial.certificate.rawBytes OR
        verificationMaterial.x509CertificateChain.certificates
      - messageSignature.signature OR dsseEnvelope.signature/signatures

    This blocks the trivially-forgeable truthy check (e.g. ``{'sigstore': 'fake'}``
    or ``{'sigstore_bundle': True}``) while remaining zero-dependency.
    """
    if not isinstance(bundle, dict):
        return False
    media = bundle.get("mediaType")
    if not (
        isinstance(media, str)
        and media.startswith("application/vnd.dev.sigstore.bundle")
    ):
        return False
    material = bundle.get("verificationMaterial")
    if not isinstance(material, dict):
        return False
    certificate = material.get("certificate")
    has_cert = isinstance(certificate, dict) and bool(certificate.get("rawBytes"))
    chain = material.get("x509CertificateChain")
    has_chain = isinstance(chain, dict) and bool(chain.get("certificates"))
    if not (has_cert or has_chain):
        return False
    message_signature = bundle.get("messageSignature")
    has_message_signature = isinstance(message_signature, dict) and bool(
        message_signature.get("signature")
    )
    dsse = bundle.get("dsseEnvelope")
    has_dsse = isinstance(dsse, dict) and bool(
        dsse.get("signature") or dsse.get("signatures")
    )
    return has_message_signature or has_dsse


def _receipt_is_signed(receipt: Dict[str, Any]) -> bool:
    """Return True when a receipt carries a structurally-valid Sigstore bundle.

    D4: Agent receipts have no Sigstore path — always return False.
    For commit receipts, mere truthiness of extensions.sigstore/sigstore_bundle
    is NOT sufficient; we require a structurally-valid bundle dict shape (see
    _is_structurally_valid_sigstore_bundle_dict).
    """
    # D4: agent receipts are never signed via Sigstore.
    if is_agent_receipt(receipt):
        return False
    extensions = receipt.get("extensions", {})
    if not isinstance(extensions, dict):
        return False
    # Check both the inline bundle dict and the bare sigstore key.
    bundle = extensions.get("sigstore_bundle")
    if _is_structurally_valid_sigstore_bundle_dict(bundle):
        return True
    # extensions.sigstore may itself be a bundle dict (some older emitters).
    sigstore = extensions.get("sigstore")
    if _is_structurally_valid_sigstore_bundle_dict(sigstore):
        return True
    return False


def _backfill_signing_metadata(index: Dict[str, Any], ledger_path: Path) -> None:
    """Populate signed/unsigned counts and per-commit flags by scanning the ledger."""
    commits = index.get("commits", {})
    if not isinstance(commits, dict):
        commits = {}
        index["commits"] = commits

    signed_count = 0
    unsigned_count = 0
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                receipt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(receipt, dict):
                continue
            sha = receipt.get("commit", {}).get("sha", "")
            if not isinstance(sha, str) or not sha:
                continue
            is_signed = _receipt_is_signed(receipt)
            if is_signed:
                signed_count += 1
            else:
                unsigned_count += 1
            entry = commits.get(sha)
            if isinstance(entry, dict):
                entry["signed"] = is_signed

    index["signed_receipt_count"] = signed_count
    index["unsigned_receipt_count"] = unsigned_count


def _save_index(index_path: Path, index: Dict[str, Any]) -> None:
    """Atomically write the ledger index."""
    tmp = index_path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW, 0o600)
    if _HAS_FCHMOD:
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp), str(index_path))


def _receipt_dedup_key(receipt: Dict[str, Any]) -> Optional[str]:
    """Return the deduplication key for a receipt.

    - Commit receipts (type aiir.commit_receipt): keyed by ``commit.sha``.
    - Review receipts (type aiir.review_receipt): keyed by ``receipt_id``
      (each review receipt is uniquely addressable by its content-addressed id).
    - Other receipt types with a ``receipt_id``: keyed by ``receipt_id``.
    - Receipts without any usable key: return None (will be skipped).
    """
    rtype = receipt.get("type", "")
    if rtype == "aiir.review_receipt":
        rid = receipt.get("receipt_id", "")
        return f"review:{rid}" if rid else None
    # Agent receipts (aiir/agent_receipt.v0.1) are content-addressed by
    # ``record_id`` and carry no commit SHA, so key them by record_id.
    if str(receipt.get("contract_version", "")).startswith("aiir/agent_receipt"):
        rid = receipt.get("record_id", "")
        return f"agent:{rid}" if rid else None
    # Default: commit receipt — key by commit SHA.
    sha = receipt.get("commit", {}).get("sha", "")
    return sha if sha else None


def append_to_ledger(
    receipts: List[Dict[str, Any]],
    ledger_dir: Optional[str] = None,
) -> Tuple[int, int, str]:
    """Append receipts to the JSONL ledger, skipping duplicates.

    Supports both commit receipts (``type: aiir.commit_receipt``) and review
    receipts (``type: aiir.review_receipt``).  Commit receipts are deduplicated
    by ``commit.sha``; review receipts are deduplicated by ``receipt_id``.

    An advisory file lock (.aiir/.lock) is held for the duration of the
    append+index transaction to prevent concurrent-run corruption.

    Returns (appended_count, skipped_count, ledger_path_str).
    """
    dir_path, ledger_path, index_path = _ledger_paths(ledger_dir)

    # Path-traversal guard — same logic as write_receipt.
    cwd_resolved = Path(os.getcwd()).resolve()
    try:
        dir_path.relative_to(cwd_resolved)
    except ValueError:
        raise ValueError(
            f"ledger dir must be within the working directory: "
            f"{dir_path} resolves outside {cwd_resolved}"
        )
    dir_path.mkdir(parents=True, exist_ok=True)
    # Re-verify after mkdir (symlink TOCTOU defence).
    real_dir = dir_path.resolve()
    try:
        real_dir.relative_to(cwd_resolved)
    except ValueError:  # pragma: no cover — TOCTOU race
        raise ValueError(
            "ledger dir escaped working directory after creation "
            "(possible symlink attack)"
        )

    with _LedgerLock(dir_path):
        index = _load_index(index_path)
        known_commits: Dict[str, Any] = index.get("commits", {})

        appended = 0
        skipped = 0

        # Append new receipts — open once, write all, then flush.
        fd = os.open(
            str(ledger_path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | _O_NOFOLLOW,
            0o600,
        )
        if _HAS_FCHMOD:
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for receipt in receipts:
                dedup_key = _receipt_dedup_key(receipt)
                if not dedup_key:
                    continue

                # Dedup: skip if this key is already in the index.
                if dedup_key in known_commits:
                    skipped += 1
                    continue

                line = _canonical_json(receipt)
                f.write(line + "\n")
                appended += 1

                # D1: Agent receipts are NOT commit receipts — their
                # ai_attestation/commit/ai fields are unauthenticated grafts and
                # MUST NOT contribute to ai/bot/author/ai_percentage aggregates.
                _is_agent = is_agent_receipt(receipt)

                is_signed = _receipt_is_signed(receipt)
                # Agent receipts identify by record_id rather than receipt_id.
                rid = receipt.get("receipt_id") or receipt.get("record_id", "")
                ts = receipt.get("timestamp", "")

                if _is_agent:
                    # Agent receipt: no ai_attestation, no commit author, no
                    # ai/bot/author counts.  Track agent_receipt_count only.
                    index["agent_receipt_count"] = (
                        index.get("agent_receipt_count", 0) + 1
                    )
                    known_commits[dedup_key] = {
                        "receipt_id": rid,
                        "signed": is_signed,
                        "line": index.get("receipt_count", 0) + appended,
                    }
                else:
                    # Commit or review receipt: read authenticated fields.
                    is_ai = receipt.get("ai_attestation", {}).get(
                        "is_ai_authored", False
                    )
                    is_bot = receipt.get("ai_attestation", {}).get(
                        "is_bot_authored", False
                    )
                    authorship = receipt.get("ai_attestation", {}).get(
                        "authorship_class", "human"
                    )

                    # For commit receipts, author comes from commit.author.email.
                    # For review receipts, author comes from reviewer.email.
                    rtype = receipt.get("type", "")
                    if rtype == "aiir.review_receipt":
                        author_email = receipt.get("reviewer", {}).get("email", "")
                    else:
                        author_email = (
                            receipt.get("commit", {}).get("author", {}).get("email", "")
                        )

                    known_commits[dedup_key] = {
                        "receipt_id": rid,
                        "ai": is_ai,
                        "bot": is_bot,
                        "authorship_class": authorship,
                        "signed": is_signed,
                        "author": author_email,
                        "line": index.get("receipt_count", 0) + appended,
                    }
                    if is_ai:
                        index["ai_commit_count"] = index.get("ai_commit_count", 0) + 1
                    if is_bot:
                        index["bot_commit_count"] = index.get("bot_commit_count", 0) + 1

                if is_signed:
                    index["signed_receipt_count"] = (
                        index.get("signed_receipt_count", 0) + 1
                    )
                else:
                    index["unsigned_receipt_count"] = (
                        index.get("unsigned_receipt_count", 0) + 1
                    )
                if index.get("first_receipt") is None:
                    index["first_receipt"] = ts
                index["latest_timestamp"] = ts

        index["receipt_count"] = index.get("receipt_count", 0) + appended
        index["commits"] = known_commits
        # Compute derived stats.
        authors = {
            v.get("author", "")
            for v in known_commits.values()
            if isinstance(v, dict) and v.get("author")
        }
        index["unique_authors"] = len(authors)
        # D1: denominator for ai_percentage is commit-receipt population only
        # (entries with "ai" key), NOT total receipt_count which includes agents.
        commit_count = sum(
            1 for v in known_commits.values() if isinstance(v, dict) and "ai" in v
        )
        index["ai_percentage"] = (
            round(index.get("ai_commit_count", 0) / commit_count * 100, 1)
            if commit_count > 0
            else 0.0
        )
        _save_index(index_path, index)

    return appended, skipped, str(ledger_path)


def export_ledger(
    ledger_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Bundle the .aiir/ ledger into a portable JSON export.

    Returns a dict suitable for serialization.  The format is designed so
    that managed services can ingest it in a single upload.
    """
    dir_path, ledger_path, index_path = _ledger_paths(ledger_dir)

    # Load existing data.
    index = _load_index(index_path)
    config = _load_config(str(dir_path))
    receipts: List[Dict[str, Any]] = []
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    receipts.append(json.loads(line))
                except json.JSONDecodeError:  # pragma: no cover
                    continue

    evidence_stream = import_evidence_stream(receipts)
    return {
        "format": "aiir.export.v1",
        "exported_at": _now_rfc3339(),
        "instance_id": config.get("instance_id"),
        "namespace": config.get("namespace"),
        "index": index,
        "receipts": receipts,
        "evidence_stream": evidence_stream,
        "evidence_summary": summarize_evidence_stream(evidence_stream),
    }
