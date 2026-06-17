# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — Sigstore signing and verification (optional dependency).

"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiir._core import (
    MAX_RECEIPT_FILE_SIZE,
    _HAS_FCHMOD,
)


_DEFAULT_SIGSTORE_OIDC_ISSUER = "https://oauth2.sigstore.dev/auth"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _format_integrated_time(value: Any) -> Optional[str]:
    text = str(value or "")
    if not text.isdigit():
        return None
    try:
        return datetime.fromtimestamp(int(text), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return None


def summarize_sigstore_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    verification_material = bundle.get("verificationMaterial")
    certificate = (
        verification_material.get("certificate")
        if isinstance(verification_material, dict)
        else None
    )
    certificate_raw = (
        certificate.get("rawBytes") if isinstance(certificate, dict) else None
    )
    certificate_sha256 = None
    if isinstance(certificate_raw, str) and certificate_raw:
        try:
            certificate_sha256 = (
                "sha256:"
                + hashlib.sha256(
                    base64.b64decode(certificate_raw, validate=True)
                ).hexdigest()
            )
        except (ValueError, TypeError):
            certificate_sha256 = None

    tlog_entries = (
        verification_material.get("tlogEntries")
        if isinstance(verification_material, dict)
        else None
    )
    entries: List[Dict[str, Any]] = []
    if isinstance(tlog_entries, list):
        for entry in tlog_entries:
            if not isinstance(entry, dict):
                continue
            integrated_time = entry.get("integratedTime")
            entries.append(
                {
                    "kind": (entry.get("kindVersion") or {}).get("kind"),
                    "log_index": entry.get("logIndex"),
                    "log_id": (entry.get("logId") or {}).get("keyId"),
                    "integrated_time": integrated_time,
                    "integrated_time_rfc3339": _format_integrated_time(integrated_time),
                    "has_signed_entry_timestamp": bool(
                        (entry.get("inclusionPromise") or {}).get(
                            "signedEntryTimestamp"
                        )
                    ),
                    "has_checkpoint": bool(
                        (
                            (entry.get("inclusionProof") or {}).get("checkpoint") or {}
                        ).get("envelope")
                    ),
                }
            )

    message_signature = bundle.get("messageSignature")
    message_digest = (
        message_signature.get("messageDigest")
        if isinstance(message_signature, dict)
        else None
    )
    timestamp_data = (
        verification_material.get("timestampVerificationData")
        if isinstance(verification_material, dict)
        else None
    )
    timestamps = (
        timestamp_data.get("rfc3161Timestamps")
        if isinstance(timestamp_data, dict)
        else None
    )

    summary: Dict[str, Any] = {
        "media_type": bundle.get("mediaType"),
        "certificate_present": bool(certificate_raw),
        "tlog_entry_count": len(entries),
        "entries": entries,
        "message_digest_algorithm": (
            message_digest.get("algorithm")
            if isinstance(message_digest, dict)
            else None
        ),
        "message_digest": (
            message_digest.get("digest") if isinstance(message_digest, dict) else None
        ),
        "rfc3161_timestamp_count": len(timestamps)
        if isinstance(timestamps, list)
        else 0,
    }
    if certificate_sha256:
        summary["certificate_sha256"] = certificate_sha256
    return summary


def validate_sigstore_bundle(
    artifact_bytes: bytes,
    bundle: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []
    artifact_sha256 = hashlib.sha256(artifact_bytes).digest()
    artifact_sha256_hex = artifact_sha256.hex()
    artifact_sha256_b64 = base64.b64encode(artifact_sha256).decode("ascii")

    media_type = bundle.get("mediaType")
    if media_type != "application/vnd.dev.sigstore.bundle.v0.3+json":
        errors.append(f"unexpected mediaType: {media_type!r}")

    message_signature = bundle.get("messageSignature")
    if not isinstance(message_signature, dict):
        errors.append("missing messageSignature block")
        return errors

    message_digest = message_signature.get("messageDigest")
    if not isinstance(message_digest, dict):
        errors.append("missing messageDigest block")
        return errors

    if message_digest.get("algorithm") != "SHA2_256":
        errors.append(
            f"unexpected messageDigest.algorithm: {message_digest.get('algorithm')!r}"
        )
    if not hmac.compare_digest(
        str(message_digest.get("digest") or ""), artifact_sha256_b64
    ):
        errors.append("messageDigest.digest does not match artifact sha256")

    signature_content = message_signature.get("signature")
    if not isinstance(signature_content, str) or not signature_content:
        errors.append("missing messageSignature.signature")

    verification_material = bundle.get("verificationMaterial")
    if not isinstance(verification_material, dict):
        errors.append("missing verificationMaterial block")
        return errors

    tlog_entries = verification_material.get("tlogEntries")
    if not isinstance(tlog_entries, list) or not tlog_entries:
        errors.append("bundle is missing Rekor tlog entries")
        return errors

    for index, entry in enumerate(tlog_entries, start=1):
        if not isinstance(entry, dict):
            errors.append(f"tlog entry {index} is not an object")
            continue

        kind = (entry.get("kindVersion") or {}).get("kind")
        if kind != "hashedrekord":
            errors.append(f"tlog entry {index} has unexpected kind: {kind!r}")

        integrated_time = entry.get("integratedTime")
        if not str(integrated_time or "").isdigit():
            errors.append(f"tlog entry {index} has invalid integratedTime")

        if not (entry.get("inclusionPromise") or {}).get("signedEntryTimestamp"):
            errors.append(f"tlog entry {index} is missing signedEntryTimestamp")

        checkpoint = (entry.get("inclusionProof") or {}).get("checkpoint") or {}
        checkpoint_envelope = checkpoint.get("envelope", "")
        if "rekor.sigstore.dev" not in checkpoint_envelope:
            errors.append(
                f"tlog entry {index} checkpoint does not reference rekor.sigstore.dev"
            )

        canonicalized_body = entry.get("canonicalizedBody")
        if not isinstance(canonicalized_body, str) or not canonicalized_body:
            errors.append(f"tlog entry {index} is missing canonicalizedBody")
            continue

        try:
            rekor_body = json.loads(
                base64.b64decode(canonicalized_body, validate=True).decode("utf-8")
            )
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"tlog entry {index} canonicalizedBody is invalid: {exc}")
            continue

        rekor_hash = ((rekor_body.get("spec") or {}).get("data") or {}).get(
            "hash"
        ) or {}
        if rekor_hash.get("algorithm") != "sha256":
            errors.append(f"tlog entry {index} hash algorithm is not sha256")
        if not hmac.compare_digest(
            str(rekor_hash.get("value") or ""), artifact_sha256_hex
        ):
            errors.append(f"tlog entry {index} hash does not match artifact sha256")

        rekor_signature = (rekor_body.get("spec") or {}).get("signature") or {}
        if not hmac.compare_digest(
            str(rekor_signature.get("content") or ""), str(signature_content or "")
        ):
            errors.append(
                f"tlog entry {index} signature content does not match bundle signature"
            )

        public_key = rekor_signature.get("publicKey")
        if not isinstance(public_key, dict):
            errors.append(f"tlog entry {index} is missing publicKey metadata")
            continue
        if public_key.get("url") or public_key.get("urls"):
            errors.append(f"tlog entry {index} uses external public key URLs")
        if not public_key.get("content"):
            errors.append(f"tlog entry {index} publicKey.content is missing")

    return errors


def _sigstore_available() -> bool:
    """Check if the sigstore package is available for import."""
    try:
        importlib.import_module("sigstore")
        return True
    except ImportError:
        return False


def sign_receipt(receipt_json_bytes: bytes) -> str:
    """Sign receipt bytes using Sigstore keyless signing.

    Uses ambient OIDC credentials in CI (GitHub Actions, GitLab CI, etc.)
    or falls back to interactive browser-based OIDC flow for local use.

    Returns the Sigstore bundle as a JSON string.
    """
    try:
        from sigstore.models import ClientTrustConfig
        from sigstore.oidc import IdentityToken, Issuer, detect_credential
        from sigstore.sign import SigningContext
    except ImportError:
        raise RuntimeError(
            "Sigstore signing requires the 'sigstore' package.\n"
            "Install with: pip install sigstore"
        )

    # Try ambient credential first (GitHub Actions, GitLab CI, etc.)
    raw_token = detect_credential()
    if raw_token is not None:
        identity_token = IdentityToken(raw_token)
    else:
        # Detect CI environment — if we're in CI but have no ambient
        # credential, the user is missing permissions (e.g., id-token: write)
        # or this is a fork PR (which can't get OIDC tokens).
        # Give a clear error instead of hanging on interactive browser flow.
        ci_env = (
            os.environ.get("CI")
            or os.environ.get("GITHUB_ACTIONS")
            or os.environ.get("GITLAB_CI")
            or os.environ.get("BITBUCKET_BUILD_NUMBER")
            or os.environ.get("CIRCLECI")
            or os.environ.get("JENKINS_URL")
            or os.environ.get("TF_BUILD")  # Azure Pipelines
        )
        if ci_env:
            hints = []
            if os.environ.get("GITHUB_ACTIONS"):
                hints.append(
                    "  - Add 'permissions: { id-token: write }' to your workflow"
                )
                if (
                    os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
                ):  # pragma: no cover
                    hints.append(
                        "  - Fork PRs cannot obtain OIDC tokens — use 'sign: false' for fork PRs"
                    )
            elif os.environ.get("GITLAB_CI"):  # pragma: no cover
                hints.append("  - Ensure CI_JOB_JWT or SIGSTORE_ID_TOKEN is available")
            hint_text = (
                "\n".join(hints)
                if hints
                else (
                    "  - Ensure OIDC credentials are available in this CI environment\n"
                    "  - Or set SIGSTORE_ID_TOKEN in your pipeline\n"
                    "  - Or disable signing with --no-sign / sign: false"
                )
            )
            raise RuntimeError(
                "Sigstore signing failed: no ambient OIDC credential detected.\n"
                "This usually means the CI runner cannot obtain an identity token.\n"
                f"{hint_text}"
            )
        # Local development — fall back to interactive OIDC flow (opens browser)
        issuer_url = os.environ.get(
            "SIGSTORE_OIDC_ISSUER", _DEFAULT_SIGSTORE_OIDC_ISSUER
        )
        force_oob = (
            os.environ.get("SIGSTORE_OAUTH_FORCE_OOB", "").strip().lower()
            in _TRUTHY_ENV_VALUES
        )
        issuer = Issuer(issuer_url)  # pragma: no cover
        identity_token = issuer.identity_token(force_oob=force_oob)  # pragma: no cover

    config = ClientTrustConfig.production()
    ctx = SigningContext.from_trust_config(config)
    with ctx.signer(identity_token) as signer:
        bundle = signer.sign_artifact(receipt_json_bytes)
    result: str = bundle.to_json()
    return result


def sign_receipt_file(receipt_path: str) -> str:
    """Sign a receipt file and write the Sigstore bundle alongside it.

    Given 'receipt_abc.json', writes 'receipt_abc.json.sigstore'.
    Returns the bundle file path.
    """
    path = Path(receipt_path)
    try:
        path.lstat()
    except FileNotFoundError:
        raise FileNotFoundError(f"Receipt file not found: {receipt_path}")
    except OSError as e:
        raise ValueError(f"Cannot stat receipt file: {e}") from e

    # Reject symlinks to prevent signing arbitrary files (info leak)
    if path.is_symlink():
        raise ValueError(
            f"Receipt file is a symlink (refusing to sign): {receipt_path}"
        )

    # Cap file size before loading into memory.
    # verify_receipt_file has a 50 MB cap but sign_receipt_file did not,
    # allowing a 1 GB file to be loaded entirely into RAM.
    try:
        file_size = path.stat().st_size
    except OSError as e:
        raise ValueError(f"Cannot stat receipt file: {e}") from e
    if file_size > MAX_RECEIPT_FILE_SIZE:
        raise ValueError(
            f"Receipt file too large for signing ({file_size} bytes, max {MAX_RECEIPT_FILE_SIZE})"
        )

    receipt_bytes = path.read_bytes()

    # Validate content is JSON before sending to Sigstore
    try:
        json.loads(receipt_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError(
            f"Receipt file is not valid JSON (refusing to sign): {receipt_path}"
        )

    # Check for existing bundle BEFORE expensive OIDC signing — avoids
    # wasting the token if the bundle already exists.
    bundle_path = str(path) + ".sigstore"
    if os.path.exists(bundle_path):
        raise FileExistsError(
            f"Sigstore bundle already exists: {bundle_path} — "
            f"remove it first or use a different receipt path"
        )

    bundle_json = sign_receipt(receipt_bytes)

    try:
        fd = os.open(bundle_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise FileExistsError(
            f"Sigstore bundle already exists: {bundle_path} — "
            f"remove it first or use a different receipt path"
        )
    if _HAS_FCHMOD:
        os.fchmod(fd, 0o600)  # Force owner-only permissions regardless of umask
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(bundle_json)
    return bundle_path


def verify_receipt_signature(
    receipt_path: str,
    bundle_path: Optional[str] = None,
    expected_identity: Optional[str] = None,
    expected_issuer: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a receipt's Sigstore signature bundle.

    Args:
        receipt_path: Path to the receipt JSON file.
        bundle_path: Path to the .sigstore bundle. If None, looks for
            <receipt_path>.sigstore.
        expected_identity: Expected signer identity (email or OIDC subject).
            If None, accepts any signer (UnsafeNoOp policy).
        expected_issuer: Expected OIDC issuer URL.

    Returns a dict with verification results.
    """
    rpath = Path(receipt_path)
    if not rpath.exists():
        return {"valid": False, "error": f"Receipt not found: {receipt_path}"}
    # Reject symlinks to prevent probing arbitrary files
    if rpath.is_symlink():
        return {
            "valid": False,
            "error": f"Receipt file is a symlink (refusing to verify): {receipt_path}",
        }

    if bundle_path is None:
        bundle_path = str(rpath) + ".sigstore"
    bpath = Path(bundle_path)
    if not bpath.exists():
        return {
            "valid": False,
            "error": f"Sigstore bundle not found: {bundle_path}",
        }
    # Reject symlinks for bundle path as well
    if bpath.is_symlink():
        return {
            "valid": False,
            "error": f"Bundle file is a symlink (refusing to verify): {bundle_path}",
        }

    # Reject oversized files to prevent memory exhaustion
    for fpath, label in [(rpath, "Receipt"), (bpath, "Bundle")]:
        try:
            fsize = fpath.stat().st_size
        except OSError as e:
            return {"valid": False, "error": f"Cannot stat {label.lower()}: {e}"}
        if fsize > MAX_RECEIPT_FILE_SIZE:
            return {
                "valid": False,
                "error": f"{label} too large ({fsize} bytes, max {MAX_RECEIPT_FILE_SIZE})",
            }

    try:
        from sigstore.models import Bundle
        from sigstore.verify import Verifier
        from sigstore.verify.policy import Identity, UnsafeNoOp
    except ImportError:
        raise RuntimeError(
            "Sigstore verification requires the 'sigstore' package.\n"
            "Install with: pip install sigstore"
        )

    try:
        receipt_bytes = rpath.read_bytes()
        bundle_text = bpath.read_text(encoding="utf-8")
        bundle_json = json.loads(bundle_text)
        if not isinstance(bundle_json, dict):
            raise ValueError("bundle JSON must be an object")
        bundle_summary = summarize_sigstore_bundle(bundle_json)
        bundle_errors = validate_sigstore_bundle(receipt_bytes, bundle_json)
        if bundle_errors:
            result: Dict[str, Any] = {
                "valid": False,
                "signature_valid": False,
                "error": bundle_errors[0],
                "errors": bundle_errors,
                "bundle": bundle_summary,
            }
            if expected_identity:
                result["expected_identity"] = expected_identity
            if expected_issuer:
                result["expected_issuer"] = expected_issuer
            return result

        bundle = Bundle.from_json(bundle_text)
        verifier = Verifier.production()

        policy: Any
        if expected_identity:
            policy = Identity(
                identity=expected_identity,
                issuer=expected_issuer,
            )
        else:
            policy = UnsafeNoOp()

        verifier.verify_artifact(receipt_bytes, bundle, policy)

        result = {
            "valid": True,
            "signature_valid": True,
            "receipt_path": str(receipt_path),
            "bundle_path": str(bundle_path),
            "policy": "identity" if expected_identity else "any",
            "bundle": bundle_summary,
        }
        if expected_identity:
            result["expected_identity"] = expected_identity
        if expected_issuer:
            result["expected_issuer"] = expected_issuer
        return result
    except Exception as e:
        # Sanitize error to prevent leaking internal paths or OIDC details
        error_msg = str(e)
        # Strip potential file paths and tokens from error messages
        safe_error = error_msg.split("\n")[0][:200]  # First line, capped
        # Redact filesystem paths — previously missed here, unlike
        # _run_git and _sanitize_error which both apply this regex.
        safe_error = re.sub(r"/[\w./-]{5,}", "<path>", safe_error)
        return {
            "valid": False,
            "signature_valid": False,
            "error": safe_error,
        }
