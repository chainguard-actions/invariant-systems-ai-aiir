# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — standalone agent receipts (aiir/agent_receipt.v0.1).

The agent-receipt profile records a single agent action (read, edit, run,
test, build, review, browse, …) as a portable, content-addressed receipt that
may later compose into a commit receipt. It shares the commit profile's
canonicalization (aiir-canon-0), hash construction, and trust ladder; only the
*subject* differs — an agent action rather than a git commit.

The record_id is ``a1-`` + the first 32 hex chars of the content hash, where
content_hash = SHA-256 of the canonical JSON of the *record core*. The record
core is the receipt minus ``record_id``, minus ``proof.content_hash`` /
``proof.signature``, and minus ``extensions`` (extensions never enter the
hash in v0.1). See docs/integrations/agent-receipt-contract.md and
schemas/test-vectors/agent_receipt_vectors.v0.1.json.
"""

from __future__ import annotations

import hmac
from typing import Any, Dict, List, Optional, Sequence

from aiir._core import (
    _canonical_json,
    _check_json_depth,
    _now_rfc3339,
    _sha256,
    _strip_terminal_escapes,
)

AGENT_RECEIPT_CONTRACT_VERSION = "aiir/agent_receipt.v0.1"
AGENT_RECEIPT_ID_PREFIX = "a1-"
AGENT_CANONICALIZATION = "aiir-canon-0"

# The fields that enter the content hash (the record core). ``proof`` is in the
# core but only carries ``canonicalization`` there — content_hash/signature are
# added to the emitted receipt's proof object, outside the hash.
AGENT_RECORD_CORE_KEYS = frozenset(
    {"contract_version", "timestamp", "actor", "action", "artifacts", "policy", "proof"}
)

_MAX_DEPTH = 64
_MAX_REASONS = 50
_MAX_ARTIFACTS = 200
_STR_CAP = 500


def is_agent_receipt(receipt: Any) -> bool:
    """Return True when the object looks like an AIIR agent receipt."""

    return (
        isinstance(receipt, dict)
        and receipt.get("contract_version") == AGENT_RECEIPT_CONTRACT_VERSION
    )


def _clean(value: Any, *, field: str, limit: int = _STR_CAP) -> str:
    """Sanitize a required string field (strip terminal escapes, cap length)."""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, got {type(value).__name__}")
    cleaned = _strip_terminal_escapes(value)[:limit]
    if not cleaned:
        raise ValueError(f"{field} must be a non-empty string")
    return cleaned


def _clean_optional(value: Any, *, field: str, limit: int = _STR_CAP) -> Optional[str]:
    """Sanitize an optional string field; return None when absent."""

    if value is None:
        return None
    return _clean(value, field=field, limit=limit)


def _normalize_actor(actor: Any) -> Dict[str, Any]:
    """Normalize the actor sub-object (who/what performed the action)."""

    if not isinstance(actor, dict):
        raise ValueError("actor must be an object")
    tool = actor.get("tool")
    if not isinstance(tool, dict):
        raise ValueError("actor.tool must be an object")
    normalized_tool: Dict[str, Any] = {
        "name": _clean(tool.get("name"), field="actor.tool.name")
    }
    surface = _clean_optional(tool.get("surface"), field="actor.tool.surface")
    if surface is not None:
        normalized_tool["surface"] = surface
    result: Dict[str, Any] = {
        "kind": _clean(actor.get("kind"), field="actor.kind", limit=80),
        "tool": normalized_tool,
    }
    session_ref = _clean_optional(actor.get("session_ref"), field="actor.session_ref")
    if session_ref is not None:
        result["session_ref"] = session_ref
    return result


def _normalize_action(action: Any) -> Dict[str, Any]:
    """Normalize the action sub-object (what happened)."""

    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    result: Dict[str, Any] = {
        "kind": _clean(action.get("kind"), field="action.kind", limit=80)
    }
    intent = _clean_optional(action.get("intent"), field="action.intent", limit=200)
    if intent is not None:
        result["intent"] = intent
    summary = _clean_optional(action.get("summary"), field="action.summary", limit=2000)
    if summary is not None:
        result["summary"] = summary
    return result


def _normalize_artifact(entry: Any, *, where: str) -> Dict[str, Any]:
    """Normalize a single artifact entry (type + ref [+ role])."""

    if not isinstance(entry, dict):
        raise ValueError(f"{where} entry must be an object")
    result: Dict[str, Any] = {
        "type": _clean(entry.get("type"), field=f"{where}.type", limit=80),
        "ref": _clean(entry.get("ref"), field=f"{where}.ref"),
    }
    role = _clean_optional(entry.get("role"), field=f"{where}.role", limit=80)
    if role is not None:
        result["role"] = role
    return result


def _normalize_artifacts(artifacts: Any) -> Dict[str, Any]:
    """Normalize the artifacts object (inputs/outputs arrays, order preserved)."""

    if artifacts is None:
        artifacts = {}
    if not isinstance(artifacts, dict):
        raise ValueError("artifacts must be an object")
    out: Dict[str, Any] = {}
    for side in ("inputs", "outputs"):
        items = artifacts.get(side, [])
        if not isinstance(items, list):
            raise ValueError(f"artifacts.{side} must be an array")
        if len(items) > _MAX_ARTIFACTS:
            raise ValueError(f"artifacts.{side} exceeds {_MAX_ARTIFACTS} entries")
        out[side] = [
            _normalize_artifact(entry, where=f"artifacts.{side}") for entry in items
        ]
    return out


def _normalize_policy(policy: Any) -> Dict[str, Any]:
    """Normalize the policy object (decision [+ reasons] [+ contract_ref])."""

    if policy is None:
        policy = {"decision": "not_evaluated"}
    if not isinstance(policy, dict):
        raise ValueError("policy must be an object")
    result: Dict[str, Any] = {
        "decision": _clean(policy.get("decision"), field="policy.decision", limit=80)
    }
    reasons = policy.get("reasons")
    if reasons is not None:
        if not isinstance(reasons, list):
            raise ValueError("policy.reasons must be an array")
        if len(reasons) > _MAX_REASONS:
            raise ValueError(f"policy.reasons exceeds {_MAX_REASONS} entries")
        result["reasons"] = [
            _clean(r, field="policy.reasons[]", limit=200) for r in reasons
        ]
    contract_ref = _clean_optional(
        policy.get("contract_ref"), field="policy.contract_ref"
    )
    if contract_ref is not None:
        result["contract_ref"] = contract_ref
    return result


def _build_record_core(
    *,
    timestamp: Any,
    actor: Any,
    action: Any,
    artifacts: Any,
    policy: Any,
) -> Dict[str, Any]:
    """Construct the canonical record core that feeds the content hash.

    Used by both ``build_agent_receipt`` (from arguments) and
    ``verify_agent_receipt`` (from a stored receipt) so the two are guaranteed
    to canonicalize identically.
    """

    core: Dict[str, Any] = {
        "contract_version": AGENT_RECEIPT_CONTRACT_VERSION,
        "timestamp": _clean(timestamp, field="timestamp", limit=64),
        "actor": _normalize_actor(actor),
        "action": _normalize_action(action),
        "artifacts": _normalize_artifacts(artifacts),
        "policy": _normalize_policy(policy),
        "proof": {"canonicalization": AGENT_CANONICALIZATION},
    }
    _check_json_depth(core, max_depth=_MAX_DEPTH)
    return core


def build_agent_receipt(
    *,
    actor_kind: str,
    actor_tool_name: str,
    action_kind: str,
    timestamp: Optional[str] = None,
    actor_tool_surface: Optional[str] = None,
    actor_session_ref: Optional[str] = None,
    action_intent: Optional[str] = None,
    action_summary: Optional[str] = None,
    artifact_inputs: Optional[Sequence[Dict[str, Any]]] = None,
    artifact_outputs: Optional[Sequence[Dict[str, Any]]] = None,
    policy_decision: str = "not_evaluated",
    policy_reasons: Optional[Sequence[str]] = None,
    policy_contract_ref: Optional[str] = None,
    extensions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a content-addressed AIIR agent receipt for one agent action."""

    actor: Dict[str, Any] = {
        "kind": actor_kind,
        "tool": {
            "name": actor_tool_name,
            **({"surface": actor_tool_surface} if actor_tool_surface else {}),
        },
        **({"session_ref": actor_session_ref} if actor_session_ref else {}),
    }
    action: Dict[str, Any] = {
        "kind": action_kind,
        **({"intent": action_intent} if action_intent else {}),
        **({"summary": action_summary} if action_summary else {}),
    }
    artifacts: Dict[str, Any] = {
        "inputs": list(artifact_inputs or []),
        "outputs": list(artifact_outputs or []),
    }
    policy: Dict[str, Any] = {
        "decision": policy_decision,
        **({"reasons": list(policy_reasons)} if policy_reasons else {}),
        **({"contract_ref": policy_contract_ref} if policy_contract_ref else {}),
    }

    core = _build_record_core(
        timestamp=timestamp or _now_rfc3339(),
        actor=actor,
        action=action,
        artifacts=artifacts,
        policy=policy,
    )

    core_json = _canonical_json(core)
    digest = _sha256(core_json)
    content_hash = "sha256:" + digest
    record_id = f"{AGENT_RECEIPT_ID_PREFIX}{digest[:32]}"

    receipt: Dict[str, Any] = {
        "contract_version": core["contract_version"],
        "record_id": record_id,
        "timestamp": core["timestamp"],
        "actor": core["actor"],
        "action": core["action"],
        "artifacts": core["artifacts"],
        "policy": core["policy"],
        "proof": {
            "canonicalization": AGENT_CANONICALIZATION,
            "content_hash": content_hash,
            "signature": None,
        },
    }
    if extensions:
        receipt["extensions"] = _sanitize_extensions(extensions)
    return receipt


def _sanitize_extensions(extensions: Any) -> Dict[str, str]:
    """Sanitize the optional, non-hashed extensions block (string values only)."""

    if not isinstance(extensions, dict):
        return {}
    clean: Dict[str, str] = {}
    for key, value in extensions.items():
        if not isinstance(key, str):
            continue
        key_safe = _strip_terminal_escapes(key)[:120]
        value_safe = _strip_terminal_escapes(str(value))[:500]
        if key_safe:
            clean[key_safe] = value_safe
    return clean


def _field_is_canonical(value: Any, limit: int) -> bool:
    """Return True when *value* is a string already in normalized canonical form.

    A field is canonical when it equals ``_strip_terminal_escapes(value)[:limit]``
    — i.e. it contains no terminal escape sequences, no stripped control characters,
    and has not been truncated (the stored value is not longer than *limit*).

    This check is applied to every stored string field in ``verify_agent_receipt``
    before the content hash is recomputed, closing escape/control-byte/truncation
    collision attacks (D2): a tampered field whose dirt normalizes away would
    otherwise hash identically to the original canonical value.
    """
    if not isinstance(value, str):
        # Non-string values are caught later by _build_record_core / _clean.
        return True
    return _strip_terminal_escapes(value)[:limit] == value


def _receipt_fields_are_canonical(receipt: Dict[str, Any]) -> bool:
    """Return False if any stored string field is not in normalized canonical form.

    Checks every string field that enters the content hash, using its exact cap.
    Returns True only when all fields satisfy ``_field_is_canonical``.
    """
    # timestamp
    if not _field_is_canonical(receipt.get("timestamp"), 64):
        return False

    actor = receipt.get("actor")
    if isinstance(actor, dict):
        if not _field_is_canonical(actor.get("kind"), 80):
            return False
        tool = actor.get("tool")
        if isinstance(tool, dict):
            if not _field_is_canonical(tool.get("name"), _STR_CAP):
                return False
            if not _field_is_canonical(tool.get("surface"), _STR_CAP):
                return False
        if not _field_is_canonical(actor.get("session_ref"), _STR_CAP):
            return False

    action = receipt.get("action")
    if isinstance(action, dict):
        if not _field_is_canonical(action.get("kind"), 80):
            return False
        if not _field_is_canonical(action.get("intent"), 200):
            return False
        if not _field_is_canonical(action.get("summary"), 2000):
            return False

    artifacts = receipt.get("artifacts")
    if isinstance(artifacts, dict):
        for side in ("inputs", "outputs"):
            items = artifacts.get(side, [])
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, dict):
                        if not _field_is_canonical(entry.get("type"), 80):
                            return False
                        if not _field_is_canonical(entry.get("ref"), _STR_CAP):
                            return False
                        if not _field_is_canonical(entry.get("role"), 80):
                            return False

    policy = receipt.get("policy")
    if isinstance(policy, dict):
        if not _field_is_canonical(policy.get("decision"), 80):
            return False
        reasons = policy.get("reasons")
        if isinstance(reasons, list):
            for r in reasons:
                if not _field_is_canonical(r, 200):
                    return False
        if not _field_is_canonical(policy.get("contract_ref"), _STR_CAP):
            return False

    return True


def verify_agent_receipt(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Verify an agent receipt's content-addressed integrity (fail-closed)."""

    errors: List[str] = []
    if not isinstance(receipt, dict):
        return {
            "valid": False,
            "receipt_type": "agent_receipt",
            "record_id": "",
            "errors": ["receipt is not a JSON object"],
        }
    if receipt.get("contract_version") != AGENT_RECEIPT_CONTRACT_VERSION:
        errors.append(f"unknown contract_version: {receipt.get('contract_version')!r}")

    proof = receipt.get("proof")
    if not isinstance(proof, dict):
        errors.append("proof must be an object")
        proof = {}

    # D2: Reject before re-normalizing — bind the STORED bytes, not a projection.
    # If any string field differs from its canonical form (strip_terminal_escapes
    # applied and truncated to the field's cap), reject immediately.  Without this
    # check, _build_record_core normalizes the stored fields before hashing, so
    # escape-only, control-byte, or truncation+trailing-byte tampering produces
    # the same hash as the original clean value, allowing forgery.
    if not errors and not _receipt_fields_are_canonical(receipt):
        return {
            "valid": False,
            "receipt_type": "agent_receipt",
            "record_id": str(receipt.get("record_id", "")),
            "errors": ["receipt fields are not in canonical form"],
        }

    try:
        core = _build_record_core(
            timestamp=receipt.get("timestamp"),
            actor=receipt.get("actor"),
            action=receipt.get("action"),
            artifacts=receipt.get("artifacts"),
            policy=receipt.get("policy"),
        )
    except (ValueError, RecursionError) as exc:
        errors.append(str(exc))
        core = None

    if errors or core is None:
        return {
            "valid": False,
            "receipt_type": "agent_receipt",
            "record_id": str(receipt.get("record_id", "")),
            "errors": errors,
        }

    core_json = _canonical_json(core)
    digest = _sha256(core_json)
    expected_hash = "sha256:" + digest
    expected_id = f"{AGENT_RECEIPT_ID_PREFIX}{digest[:32]}"
    stored_hash = str(proof.get("content_hash", ""))
    stored_id = str(receipt.get("record_id", ""))

    hash_ok = hmac.compare_digest(
        stored_hash.encode("utf-8"), expected_hash.encode("utf-8")
    )
    id_ok = hmac.compare_digest(stored_id.encode("utf-8"), expected_id.encode("utf-8"))

    result: Dict[str, Any] = {
        "valid": hash_ok and id_ok,
        "receipt_type": "agent_receipt",
        "record_id": stored_id,
        "content_hash_match": hash_ok,
        "record_id_match": id_ok,
        "actor_tool": core["actor"]["tool"]["name"],
        "actor_kind": core["actor"]["kind"],
        "action_kind": core["action"]["kind"],
        "policy_decision": core["policy"]["decision"],
        "errors": [],
    }
    if result["valid"]:
        # Only expose recomputed identifiers on an already-valid receipt, so a
        # tampered receipt never learns its "correct" hash (no forgery oracle).
        result["expected_content_hash"] = expected_hash
        result["expected_record_id"] = expected_id
    return result


def format_agent_receipt_pretty(receipt: Dict[str, Any]) -> str:
    """Render a short human-readable summary of an agent receipt."""

    actor = receipt.get("actor", {}) if isinstance(receipt.get("actor"), dict) else {}
    tool = actor.get("tool", {}) if isinstance(actor.get("tool"), dict) else {}
    action = (
        receipt.get("action", {}) if isinstance(receipt.get("action"), dict) else {}
    )
    policy = (
        receipt.get("policy", {}) if isinstance(receipt.get("policy"), dict) else {}
    )
    rid = _strip_terminal_escapes(str(receipt.get("record_id", "?")))[:40]
    tool_name = _strip_terminal_escapes(str(tool.get("name", "?")))[:80]
    action_kind = _strip_terminal_escapes(str(action.get("kind", "?")))[:80]
    decision = _strip_terminal_escapes(str(policy.get("decision", "?")))[:80]
    return (
        f"Agent receipt {rid}\n"
        f"  actor:  {tool_name} ({_strip_terminal_escapes(str(actor.get('kind', '?')))[:80]})\n"
        f"  action: {action_kind}\n"
        f"  policy: {decision}"
    )
