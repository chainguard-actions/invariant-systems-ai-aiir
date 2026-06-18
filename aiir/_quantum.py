# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Quantum workload provenance helpers (stdlib-only).

Provides pure-Python functions to package, bind, and verify quantum workload
provenance bundles.  No quantum SDK dependency — works with any provider
(IBM Qiskit, Google Cirq, AWS Braket, Rigetti pyQuil, IonQ, PennyLane, …)
by recording the execution handle each SDK already exposes.

Typical 60-second workflow::

    from aiir.quantum import package, bind, verify

    # 1. Package a workload (before execution)
    pkg = package("ghz3.qasm", shots=1024)

    # 2. Run on any backend (your SDK, your way)
    #    job = sampler.run(circuit, shots=1024)

    # 3. Bind the result
    bundle = bind(pkg, job_id="abc123", backend="ibm_fez")

    # 4. Verify
    assert verify(bundle)

    # 5. Tamper and observe failure
    bundle["execution"]["job_id"] = "TAMPERED"
    assert not verify(bundle)
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Schema identifiers — vendor-agnostic by design
# ---------------------------------------------------------------------------

WORKLOAD_SCHEMA = "aiir.quantum.workload_package.v1"
EXECUTION_SCHEMA = "aiir.quantum.execution_record.v1"
BUNDLE_SCHEMA = "aiir.quantum.provenance_bundle.v1"
LOGICAL_WORKLOAD_SCHEMA = "aiir.quantum.logical_workload_identity.v1"

# Known providers (not exhaustive — any string is accepted)
PROVIDER_IBM = "ibm-quantum"
PROVIDER_BRAKET = "aws-braket"
PROVIDER_CIRQ = "google-cirq"
PROVIDER_RIGETTI = "rigetti-qcs"
PROVIDER_IONQ = "ionq"
PROVIDER_PENNYLANE = "pennylane"
PROVIDER_GENERIC = "generic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_rfc3339() -> str:
    """Return current UTC time in RFC 3339 format."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _content_hash(obj: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash of a JSON-serialisable dict."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _logical_workload_core(workload_package: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the stable logical workload identity from a workload package."""
    artifacts = workload_package.get("artifacts")
    if not isinstance(artifacts, dict):
        raise TypeError("workload artifacts must be a dict")

    qasm = artifacts.get("qasm")
    if not isinstance(qasm, str) or not qasm:
        raise TypeError("workload artifacts.qasm must be a non-empty string")

    return {
        "schema": LOGICAL_WORKLOAD_SCHEMA,
        "artifacts": {"qasm": qasm},
    }


def _logical_workload_hash(workload_package: Dict[str, Any]) -> str:
    """Hash the stable logical workload identity only."""
    return _content_hash(_logical_workload_core(workload_package))


def _package_content_hash(workload_package: Dict[str, Any]) -> str:
    """Hash the full workload package, excluding its self-hash field."""
    package_copy = copy.deepcopy(workload_package)
    package_copy.pop("content_hash", None)
    return _content_hash(package_copy)


def _binding_hash(
    workload_hash: str,
    package_hash: str,
    execution_hash: str,
) -> str:
    """Hash the binding between logical workload, package, and execution."""
    binding_input = json.dumps(
        {
            "workload": workload_hash,
            "package": package_hash,
            "execution": execution_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(binding_input).hexdigest()


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------


def package(
    qasm: str,
    *,
    shots: int = 1024,
    provider: str = PROVIDER_GENERIC,
    backend: str = "auto",
    name: str = "workload",
    description: str = "",
    optimization_level: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a vendor-agnostic quantum workload package.

    Parameters
    ----------
    qasm : str
        OpenQASM source (2.0 or 3.0).  Can be the source text itself or
        a file path ending in ``.qasm``.
    shots : int
        Number of measurement shots.
    provider : str
        Execution provider hint (e.g. ``"ibm-quantum"``, ``"aws-braket"``).
        Any string is accepted.
    backend : str
        Target backend name or ``"auto"`` for provider default.
    name : str
        Human-readable workload name.
    description : str
        Optional description.
    optimization_level : int
        Transpiler / compiler optimization level hint.
    metadata : dict, optional
        Extra key-value pairs to attach.

    Returns
    -------
    dict
        A workload package dict with a content hash.
    """
    if not isinstance(qasm, str) or not qasm.strip():
        raise ValueError("qasm must be a non-empty string")
    if not isinstance(shots, int) or shots <= 0:
        raise ValueError("shots must be a positive integer")

    # If it looks like a file path, read it
    qasm_text = qasm
    if qasm.rstrip().endswith(".qasm") and "\n" not in qasm and len(qasm) < 1024:
        import os

        if os.path.isfile(qasm):
            with open(qasm, encoding="utf-8") as fh:
                qasm_text = fh.read()

    pkg: Dict[str, Any] = {
        "schema": WORKLOAD_SCHEMA,
        "name": name,
        "provider": provider,
        "runtime": {
            "shots": shots,
            "backend": backend,
            "optimization_level": optimization_level,
        },
        "artifacts": {
            "qasm": qasm_text,
        },
        "created_at": _now_rfc3339(),
    }
    if description:
        pkg["description"] = description
    if metadata:
        pkg["metadata"] = metadata

    pkg["logical_workload_hash"] = _logical_workload_hash(pkg)
    pkg["content_hash"] = _package_content_hash(pkg)
    return pkg


# ---------------------------------------------------------------------------
# Bind
# ---------------------------------------------------------------------------


def bind(
    workload_package: Dict[str, Any],
    *,
    job_id: str,
    backend: str,
    provider: Optional[str] = None,
    session_id: Optional[str] = None,
    task_arn: Optional[str] = None,
    submitted_at: Optional[str] = None,
    result_counts: Optional[Dict[str, int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bind a runtime execution handle to a workload package.

    Parameters
    ----------
    workload_package : dict
        The package returned by :func:`package`.
    job_id : str
        The execution handle from the provider (IBM job id, Braket task id,
        Cirq job name, etc.).
    backend : str
        The backend / device name that executed the workload.
    provider : str, optional
        Override the provider from the workload package.
    session_id : str, optional
        Session or batch identifier (IBM sessions, Braket batches, etc.).
    task_arn : str, optional
        Full ARN for AWS Braket tasks.
    submitted_at : str, optional
        ISO-8601 submission timestamp (defaults to now).
    result_counts : dict, optional
        Raw measurement counts (e.g. ``{"000": 500, "111": 524}``).
    metadata : dict, optional
        Extra key-value pairs to attach.

    Returns
    -------
    dict
        A provenance bundle with workload, execution, and binding sections.
    """
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id must be a non-empty string")
    if not isinstance(backend, str) or not backend.strip():
        raise ValueError("backend must be a non-empty string")
    if not isinstance(workload_package, dict):
        raise ValueError("workload_package must be a dict")

    workload = copy.deepcopy(workload_package)
    if not isinstance(workload.get("logical_workload_hash"), str):
        workload["logical_workload_hash"] = _logical_workload_hash(workload)
    if not isinstance(workload.get("content_hash"), str):
        workload["content_hash"] = _package_content_hash(workload)

    resolved_provider = provider or workload.get("provider", PROVIDER_GENERIC)

    execution: Dict[str, Any] = {
        "schema": EXECUTION_SCHEMA,
        "provider": resolved_provider,
        "job_id": job_id,
        "backend": backend,
        "submitted_at": submitted_at or _now_rfc3339(),
    }
    if session_id:
        execution["session_id"] = session_id
    if task_arn:
        execution["task_arn"] = task_arn
    if result_counts:
        execution["result_counts"] = result_counts
    if metadata:
        execution["metadata"] = metadata

    # Keep logical workload identity stable across packaging time and provider
    # hints while still binding the exact package and execution record.
    workload_hash = workload["logical_workload_hash"]
    package_hash = workload["content_hash"]
    execution_hash = _content_hash(execution)
    binding_hash = _binding_hash(workload_hash, package_hash, execution_hash)

    bundle: Dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "workload": workload,
        "execution": execution,
        "binding": {
            "workload_hash": workload_hash,
            "package_hash": package_hash,
            "execution_hash": execution_hash,
            "binding_hash": binding_hash,
            "bound_at": _now_rfc3339(),
        },
        "created_at": _now_rfc3339(),
    }
    return bundle


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify(bundle: Dict[str, Any]) -> bool:
    """Verify a provenance bundle's internal consistency.

    Checks three things:

    1. The workload content hash matches recomputation.
    2. The execution content hash matches recomputation.
    3. The binding hash correctly ties the two together.

    Returns ``True`` if all checks pass, ``False`` otherwise.
    Does NOT verify Sigstore signatures or transparency-log inclusion —
    use ``aiir --verify`` for that.
    """
    if not isinstance(bundle, dict):
        return False

    try:
        workload = bundle["workload"]
        execution = bundle["execution"]
        binding = bundle["binding"]
        if not isinstance(workload, dict):
            return False
        if not isinstance(execution, dict):
            return False
        if not isinstance(binding, dict):
            return False

        # 1. Verify workload hash
        stored_workload_hash = binding["workload_hash"]
        recomputed_workload_hash = _logical_workload_hash(workload)
        if not _constant_time_compare(stored_workload_hash, recomputed_workload_hash):
            return False

        stored_logical_hash = workload.get("logical_workload_hash")
        if stored_logical_hash is not None and not _constant_time_compare(
            stored_logical_hash, recomputed_workload_hash
        ):
            return False

        # 2. Verify full workload package hash
        stored_package_hash = binding["package_hash"]
        recomputed_package_hash = _package_content_hash(workload)
        if not _constant_time_compare(stored_package_hash, recomputed_package_hash):
            return False

        stored_content_hash = workload.get("content_hash")
        if stored_content_hash is not None and not _constant_time_compare(
            stored_content_hash, recomputed_package_hash
        ):
            return False

        # 3. Verify execution hash
        stored_execution_hash = binding["execution_hash"]
        recomputed_execution_hash = _content_hash(execution)
        if not _constant_time_compare(stored_execution_hash, recomputed_execution_hash):
            return False

        # 4. Verify binding hash
        stored_binding_hash = binding["binding_hash"]
        recomputed_binding_hash = _binding_hash(
            stored_workload_hash,
            stored_package_hash,
            stored_execution_hash,
        )
        if not _constant_time_compare(stored_binding_hash, recomputed_binding_hash):
            return False

        return True
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _constant_time_compare(a: Any, b: Any) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac

    if not isinstance(a, str) or not isinstance(b, str):
        return False
    try:
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except UnicodeError:
        return False


# ---------------------------------------------------------------------------
# Convenience: verify_or_explain
# ---------------------------------------------------------------------------


def verify_or_explain(bundle: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Verify a bundle and return ``(ok, reasons)``.

    If verification passes, ``reasons`` is empty.
    If it fails, ``reasons`` lists which checks failed.
    """
    reasons: List[str] = []
    if not isinstance(bundle, dict):
        return False, ["bundle is not a dict"]

    try:
        workload = bundle["workload"]
        execution = bundle["execution"]
        binding = bundle["binding"]
    except KeyError as exc:
        return False, [f"missing top-level key: {exc}"]

    for key, value in (
        ("workload", workload),
        ("execution", execution),
        ("binding", binding),
    ):
        if not isinstance(value, dict):
            return False, [f"{key} is not a dict"]

    # Workload hash
    try:
        stored = binding["workload_hash"]
        recomputed = _logical_workload_hash(workload)
        if not _constant_time_compare(stored, recomputed):
            reasons.append(
                "logical workload hash mismatch (logical workload identity was modified)"
            )

        stored_logical_hash = workload.get("logical_workload_hash")
        if stored_logical_hash is not None and not _constant_time_compare(
            stored_logical_hash, recomputed
        ):
            reasons.append(
                "workload logical_workload_hash mismatch (package identity was modified)"
            )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reasons.append(f"workload hash check error: {exc}")

    # Package hash
    try:
        stored = binding["package_hash"]
        recomputed = _package_content_hash(workload)
        if not _constant_time_compare(stored, recomputed):
            reasons.append(
                "workload package hash mismatch (workload package was modified after packaging)"
            )

        stored_content_hash = workload.get("content_hash")
        if stored_content_hash is not None and not _constant_time_compare(
            stored_content_hash, recomputed
        ):
            reasons.append(
                "workload content_hash mismatch (workload package was modified after packaging)"
            )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reasons.append(f"package hash check error: {exc}")

    # Execution hash
    try:
        stored = binding["execution_hash"]
        recomputed = _content_hash(execution)
        if not _constant_time_compare(stored, recomputed):
            reasons.append(
                "execution record hash mismatch (execution record was modified after binding)"
            )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reasons.append(f"execution hash check error: {exc}")

    # Binding hash
    try:
        stored = binding["binding_hash"]
        recomputed = _binding_hash(
            binding["workload_hash"],
            binding["package_hash"],
            binding["execution_hash"],
        )
        if not _constant_time_compare(stored, recomputed):
            reasons.append("binding hash mismatch (binding was modified)")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        reasons.append(f"binding hash check error: {exc}")

    return len(reasons) == 0, reasons


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def save_bundle(bundle: Dict[str, Any], path: str) -> None:
    """Write a bundle to a JSON file."""
    import os

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2)
        fh.write("\n")


def load_bundle(path: str) -> Dict[str, Any]:
    """Read a bundle from a JSON file."""
    with open(path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    if not isinstance(bundle, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return bundle
