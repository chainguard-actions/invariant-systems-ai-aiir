# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Regression tests for the audit-2026-06-hardening workstream A changes.

Covers:
  - C2: _verify_cbor.py bytewise canonical-order guard
  - C3: _schema.py relaxed tool URI pattern
  - C4(5): _schema.py schema-aware v2 required tree_sha/parent_shas
  - C5.3: _verify.py CBOR sidecar mismatch -> valid=False
  - C5.4: _policy.py require_* always severity=error
  - C5.5: _verify_release.py enforcement validation
  - C5.6: _verify_inference.py and _verify_research_evidence.py depth guard
  - R1:   _verify.py accepts aiir.review_receipt (same hash mechanism)
  - Additional: Z-anchor regexes, array auto-detection, evidence tier labelling
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical_json(obj: Any) -> str:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


_COMMIT_CORE_KEYS = {
    "type",
    "schema",
    "version",
    "commit",
    "ai_attestation",
    "provenance",
}

_REVIEW_CORE_KEYS = {
    "type",
    "schema",
    "version",
    "reviewed_commit",
    "reviewer",
    "review_outcome",
    "comment",
    "provenance",
}


def _make_valid_commit_receipt(
    schema: str = "aiir/commit_receipt.v1", **overrides: Any
) -> Dict[str, Any]:
    """Build a structurally and hash-valid commit receipt for testing."""
    commit: Dict[str, Any] = {
        "sha": "a" * 40,
        "author": {
            "name": "Test",
            "email": "test@example.com",
            "date": "2026-01-01T00:00:00Z",
        },
        "committer": {
            "name": "Test",
            "email": "test@example.com",
            "date": "2026-01-01T00:00:00Z",
        },
        "subject": "test commit",
        "message_hash": "sha256:" + _sha256("test"),
        "diff_hash": "sha256:" + _sha256("diff"),
        "files_changed": 1,
        "files": ["test.py"],
    }
    if schema == "aiir/commit_receipt.v2":
        commit["tree_sha"] = "b" * 40
        commit["parent_shas"] = ["c" * 40]

    core = {
        "type": "aiir.commit_receipt",
        "schema": schema,
        "version": "1.6.0",
        "commit": commit,
        "ai_attestation": {
            "is_ai_authored": False,
            "signals_detected": [],
            "signal_count": 0,
            "is_bot_authored": False,
            "bot_signals_detected": [],
            "bot_signal_count": 0,
            "authorship_class": "human",
            "detection_method": "heuristic_v2",
        },
        "provenance": {
            "repository": "https://github.com/example/repo",
            "tool": "https://github.com/invariant-systems-ai/aiir@1.6.0",
            "generator": "aiir.cli",
        },
    }
    core.update(overrides)
    core_subset = {k: v for k, v in core.items() if k in _COMMIT_CORE_KEYS}
    cj = _canonical_json(core_subset)
    return {
        **core,
        "receipt_id": "g1-" + _sha256(cj)[:32],
        "content_hash": "sha256:" + _sha256(cj),
        "timestamp": "2026-01-01T00:00:00Z",
        "extensions": {},
    }


def _make_valid_review_receipt(
    *, include_comment: bool = False, **overrides: Any
) -> Dict[str, Any]:
    """Build a hash-valid review receipt for testing."""
    core: Dict[str, Any] = {
        "type": "aiir.review_receipt",
        "schema": "aiir/review_receipt.v1",
        "version": "1.6.0",
        "reviewed_commit": {
            "sha": "d" * 40,
        },
        "reviewer": {
            "name": "Reviewer",
            "email": "reviewer@example.com",
        },
        "review_outcome": "approved",
        "provenance": {
            "repository": "https://github.com/example/repo",
            "tool": "https://github.com/invariant-systems-ai/aiir@1.6.0",
            "generator": "aiir.cli",
        },
    }
    if include_comment:
        core["comment"] = "LGTM"
    core.update(overrides)
    core_subset = {k: v for k, v in core.items() if k in _REVIEW_CORE_KEYS}
    cj = _canonical_json(core_subset)
    return {
        **core,
        "receipt_id": "g1-" + _sha256(cj)[:32],
        "content_hash": "sha256:" + _sha256(cj),
        "timestamp": "2026-01-01T00:00:00Z",
        "extensions": {},
    }


def _make_research_receipt() -> Dict[str, Any]:
    """Build a minimal valid research evidence receipt."""
    from aiir._verify_research_evidence import (
        CANONICALIZATION,
        CONTRACT_VERSION,
        _compute_research_evidence_hash,
    )

    timestamp = "2026-01-01T00:00:00Z"
    subject = {
        "kind": "research_claim",
        "repo": "https://github.com/example/repo",
        "program_id": "prog-001",
        "claim_id": "claim-001",
        "title": "Test claim",
    }
    claim = {
        "status": "hypothesis",
        "summary": "Test summary",
        "non_claims": [],
        "last_reviewed": "2026-01-01",
    }
    evidence = {
        "artifacts": [{"type": "code", "ref": "main", "digest": "abc123"}],
        "verifiers": [{"type": "tool", "ref": "pytest", "digest": "def456"}],
    }
    governance = {
        "public_safe": True,
        "ip_sensitive": False,
        "disclosure_tier": "public",
        "next_gate": "peer-review",
    }
    proof_stub = {"canonicalization": CANONICALIZATION}

    h = _compute_research_evidence_hash(
        timestamp, subject, claim, evidence, governance, proof_stub
    )
    proof = {
        "canonicalization": CANONICALIZATION,
        "content_hash": f"sha256:{h}",
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "timestamp": timestamp,
        "subject": subject,
        "claim": claim,
        "evidence": evidence,
        "governance": governance,
        "proof": proof,
        "record_id": f"r1-{h[:32]}",
    }


# ===========================================================================
# C2: _verify_cbor.py — bytewise canonical order guard
# ===========================================================================


class TestCborCanonicalOrderGuard(unittest.TestCase):
    """C2: decoder guard uses bytewise comparison (RFC 8949 section 4.2.1)."""

    def test_valid_map_accepted(self):
        """A correctly-ordered CBOR map must decode without error."""
        from aiir._canonical_cbor import canonical_cbor_bytes
        from aiir._verify_cbor import decode_cbor_full

        data = {"a": 1, "b": 2}
        encoded = canonical_cbor_bytes(data)
        decoded = decode_cbor_full(encoded)
        self.assertEqual(decoded, data)

    def test_unsorted_keys_rejected(self):
        """A map with out-of-bytewise-order keys must raise CborDecodeError."""
        from aiir._verify_cbor import CborDecodeError, decode_cbor_full

        # Manually construct a two-key map where keys are in WRONG order:
        # {0x61 0x62 : 1, 0x61 0x61 : 2} => "b" before "a" — wrong order
        # CBOR: a2 61 62 01 61 61 02
        bad_map = bytes([0xA2, 0x61, 0x62, 0x01, 0x61, 0x61, 0x02])
        with self.assertRaises(CborDecodeError):
            decode_cbor_full(bad_map)

    def test_duplicate_key_same_length_rejected(self):
        """Duplicate-length keys in wrong order must be rejected bytewise."""
        from aiir._verify_cbor import CborDecodeError, decode_cbor_full

        # Map {0x62 0x62 0x61: 1, 0x62 0x61 0x62: 2} — "bba" before "bab"
        # CBOR: a2 62 62 61 01 62 61 62 02
        bad_map = bytes([0xA2, 0x62, 0x62, 0x61, 0x01, 0x62, 0x61, 0x62, 0x02])
        with self.assertRaises(CborDecodeError):
            decode_cbor_full(bad_map)

    def test_bytewise_compare_not_length_first(self):
        """Confirm we use bytewise comparison, not length-first.

        Under bytewise order, a short key whose encoded bytes are larger than
        a longer key's encoded bytes sorts AFTER the longer key.
        Both orderings agree for AIIR's text-string-only maps (empirically),
        but this test documents the new contract.
        """
        import inspect

        from aiir._verify_cbor import decode_cbor

        source = inspect.getsource(decode_cbor)
        # The new guard must not use len() tuple comparison
        self.assertNotIn("len(key_bytes), key_bytes", source)
        # Must use plain bytewise comparison
        self.assertIn("key_bytes <= prev_key_bytes", source)

    def test_docstring_mentions_rfc_8949(self):
        """The decode_cbor docstring must reference RFC 8949 section 4.2.1."""
        from aiir._verify_cbor import decode_cbor

        doc = decode_cbor.__doc__ or ""
        self.assertIn("RFC 8949", doc)


# ===========================================================================
# C3: _schema.py — relaxed tool URI pattern
# ===========================================================================


class TestToolURIPattern(unittest.TestCase):
    """C3: provenance.tool accepts any https URI, not just the AIIR repo."""

    def test_own_aiir_uri_still_valid(self):
        """AIIR's own URI must still pass."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        errors = validate_receipt_schema(r)
        self.assertEqual(errors, [], errors)

    def test_third_party_https_uri_accepted(self):
        """A legitimate third-party https URI must pass (C3 core requirement)."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["provenance"]["tool"] = "https://gitlab.com/acme/my-aiir-gen@2.0.0"
        # Recompute hash with new provenance
        core_subset = {k: v for k, v in r.items() if k in _COMMIT_CORE_KEYS}
        cj = _canonical_json(core_subset)
        r["receipt_id"] = "g1-" + _sha256(cj)[:32]
        r["content_hash"] = "sha256:" + _sha256(cj)
        errors = validate_receipt_schema(r)
        tool_errors = [e for e in errors if "tool" in e.lower()]
        self.assertEqual(
            tool_errors,
            [],
            f"Third-party HTTPS URI should be accepted, got: {tool_errors}",
        )

    def test_http_uri_rejected(self):
        """An http:// (non-https) URI must still be rejected."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["provenance"]["tool"] = "http://evil.com/tool"
        errors = validate_receipt_schema(r)
        self.assertTrue(any("tool" in e for e in errors), errors)

    def test_whitespace_in_uri_rejected(self):
        """A URI with embedded whitespace must be rejected."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["provenance"]["tool"] = "https://x\n@evil.com"
        errors = validate_receipt_schema(r)
        self.assertTrue(any("tool" in e for e in errors), errors)

    def test_error_message_mentions_example(self):
        """The error message for invalid tool must mention an example URI."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["provenance"]["tool"] = "not-a-uri"
        errors = validate_receipt_schema(r)
        tool_errors = [e for e in errors if "tool" in e]
        self.assertTrue(any("https" in e for e in tool_errors), tool_errors)


# ===========================================================================
# C4(5): _schema.py — v2 required tree_sha/parent_shas
# ===========================================================================


class TestV2RequiredDAGFields(unittest.TestCase):
    """C4 sub-decision 5: v2 receipts require tree_sha and parent_shas."""

    def test_v2_with_dag_fields_has_no_errors(self):
        """A v2 receipt that has both dag fields should produce no schema errors."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt(schema="aiir/commit_receipt.v2")
        errors = validate_receipt_schema(r)
        self.assertEqual(errors, [], errors)

    def test_v2_missing_tree_sha_is_advisory_error(self):
        """A v2 receipt missing tree_sha gets a schema advisory error."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt(schema="aiir/commit_receipt.v2")
        del r["commit"]["tree_sha"]
        errors = validate_receipt_schema(r)
        self.assertTrue(
            any("tree_sha" in e and "required" in e for e in errors),
            f"Expected tree_sha required error, got: {errors}",
        )

    def test_v2_missing_parent_shas_is_advisory_error(self):
        """A v2 receipt missing parent_shas gets a schema advisory error."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt(schema="aiir/commit_receipt.v2")
        del r["commit"]["parent_shas"]
        errors = validate_receipt_schema(r)
        self.assertTrue(
            any("parent_shas" in e and "required" in e for e in errors),
            f"Expected parent_shas required error, got: {errors}",
        )

    def test_v1_missing_dag_fields_is_not_an_error(self):
        """A v1 receipt missing tree_sha/parent_shas must NOT produce dag errors."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt(schema="aiir/commit_receipt.v1")
        # v1 receipt should not have dag fields by default in our helper
        self.assertNotIn("tree_sha", r["commit"])
        errors = validate_receipt_schema(r)
        dag_errors = [e for e in errors if "tree_sha" in e or "parent_shas" in e]
        self.assertEqual(dag_errors, [], dag_errors)

    def test_v2_missing_dag_fields_still_hash_valid(self):
        """Advisory schema error must NOT flip the hash verdict (R3+R6 test)."""
        from aiir._verify import verify_receipt

        # Build a v2 receipt, strip tree_sha AFTER computing hash
        r = _make_valid_commit_receipt(schema="aiir/commit_receipt.v2")
        # Recompute the hash without tree_sha in commit (tree_sha IS in the core)
        # A proper v2 missing tree_sha would have been hashed without it.
        # Build the receipt with no tree_sha from scratch.
        commit_no_dag = {
            "sha": "a" * 40,
            "author": {
                "name": "Test",
                "email": "test@example.com",
                "date": "2026-01-01T00:00:00Z",
            },
            "committer": {
                "name": "Test",
                "email": "test@example.com",
                "date": "2026-01-01T00:00:00Z",
            },
            "subject": "test commit",
            "message_hash": "sha256:" + _sha256("test"),
            "diff_hash": "sha256:" + _sha256("diff"),
            "files_changed": 1,
            "files": ["test.py"],
            # No tree_sha, no parent_shas
        }
        core: Dict[str, Any] = {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v2",
            "version": "1.6.0",
            "commit": commit_no_dag,
            "ai_attestation": {
                "is_ai_authored": False,
                "signals_detected": [],
                "signal_count": 0,
                "is_bot_authored": False,
                "bot_signals_detected": [],
                "bot_signal_count": 0,
                "authorship_class": "human",
                "detection_method": "heuristic_v2",
            },
            "provenance": {
                "repository": "https://github.com/example/repo",
                "tool": "https://github.com/invariant-systems-ai/aiir@1.6.0",
                "generator": "aiir.cli",
            },
        }
        core_subset = {k: v for k, v in core.items() if k in _COMMIT_CORE_KEYS}
        cj = _canonical_json(core_subset)
        receipt = {
            **core,
            "receipt_id": "g1-" + _sha256(cj)[:32],
            "content_hash": "sha256:" + _sha256(cj),
            "timestamp": "2026-01-01T00:00:00Z",
            "extensions": {},
        }
        result = verify_receipt(receipt)
        # Hash is still valid (missing dag fields are advisory only)
        self.assertTrue(
            result["valid"],
            f"Hash should be valid but got errors: {result.get('errors')}",
        )
        # Schema errors must be present
        schema_errors = result.get("schema_errors", [])
        self.assertTrue(
            any("tree_sha" in e for e in schema_errors),
            f"Expected tree_sha advisory error in schema_errors: {schema_errors}",
        )


# ===========================================================================
# C5.3: _verify.py — CBOR sidecar mismatch flips valid=False
# ===========================================================================


class TestCborSidecarValidFlip(unittest.TestCase):
    """C5.3: A present-but-mismatching CBOR sidecar must set valid=False."""

    def _write_receipt(self, tmpdir: str, receipt: Dict[str, Any]) -> str:
        """Write a receipt JSON to tmpdir and return the path."""
        p = Path(tmpdir) / "receipt.json"
        p.write_text(json.dumps(receipt), encoding="utf-8")
        return str(p)

    def test_invalid_sidecar_flips_valid_to_false(self):
        """A mismatching CBOR sidecar must make verify_receipt_file return valid=False."""
        from aiir._verify import verify_receipt_file

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = self._write_receipt(tmpdir, r)
            cbor_path = Path(receipt_path).with_suffix(".cbor")
            # Write garbage bytes as the sidecar
            cbor_path.write_bytes(b"\xff\x00\x01\x02\x03")
            result = verify_receipt_file(receipt_path)
            self.assertFalse(result["valid"], f"Expected valid=False but got: {result}")
            self.assertIn("cbor_sidecar", result)
            self.assertFalse(result["cbor_sidecar"]["valid"])

    def test_missing_sidecar_stays_valid(self):
        """A missing CBOR sidecar must NOT affect validity (missing is OK)."""
        from aiir._verify import verify_receipt_file

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = self._write_receipt(tmpdir, r)
            # No sidecar file
            result = verify_receipt_file(receipt_path)
            self.assertTrue(result["valid"], f"Expected valid=True but got: {result}")
            self.assertNotIn("cbor_sidecar", result)

    def test_valid_sidecar_stays_valid(self):
        """A matching CBOR sidecar must leave valid=True."""
        from aiir._canonical_cbor import (
            build_canonical_object_envelope,
            canonical_cbor_bytes,
        )
        from aiir._verify import verify_receipt_file

        r = _make_valid_commit_receipt()

        CORE_KEYS = {
            "type",
            "schema",
            "version",
            "commit",
            "ai_attestation",
            "provenance",
        }
        core = {k: r[k] for k in CORE_KEYS if k in r}
        rtype = str(r.get("type", "aiir.receipt"))
        kind = f"{rtype}.core"
        schema_val = str(r.get("schema", ""))

        envelope = build_canonical_object_envelope(
            kind=kind, object_schema=schema_val, core=core
        )
        cbor_bytes = canonical_cbor_bytes(envelope)

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = self._write_receipt(tmpdir, r)
            cbor_path = Path(receipt_path).with_suffix(".cbor")
            cbor_path.write_bytes(cbor_bytes)
            result = verify_receipt_file(receipt_path)
            self.assertTrue(
                result.get("valid"), f"Expected valid=True but got: {result}"
            )


# ===========================================================================
# C5.4: _policy.py — require_* always severity=error
# ===========================================================================


class TestRequireStarAlwaysError(unittest.TestCase):
    """C5.4: require_signing/require_provenance_repo/require_schema_valid are always error."""

    def _receipt_no_prov_repo(self) -> Dict[str, Any]:
        r = _make_valid_commit_receipt()
        r["provenance"]["repository"] = None
        return r

    def test_require_signing_soft_fail_still_error(self):
        """require_signing violation under soft-fail enforcement must be severity=error."""
        from aiir._policy import evaluate_receipt_policy

        policy = {"require_signing": True, "enforcement": "soft-fail"}
        violations = evaluate_receipt_policy({}, policy, is_signed=False)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, "error")

    def test_require_signing_warn_still_error(self):
        """require_signing violation under warn enforcement must be severity=error."""
        from aiir._policy import evaluate_receipt_policy

        policy = {"require_signing": True, "enforcement": "warn"}
        violations = evaluate_receipt_policy({}, policy, is_signed=False)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, "error")

    def test_require_signing_hard_fail_is_error(self):
        """require_signing violation under hard-fail must also be severity=error."""
        from aiir._policy import evaluate_receipt_policy

        policy = {"require_signing": True, "enforcement": "hard-fail"}
        violations = evaluate_receipt_policy({}, policy, is_signed=False)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].severity, "error")

    def test_require_provenance_repo_soft_fail_error(self):
        """require_provenance_repo violation under soft-fail must be severity=error."""
        from aiir._policy import evaluate_receipt_policy

        receipt = self._receipt_no_prov_repo()
        policy = {"require_provenance_repo": True, "enforcement": "soft-fail"}
        violations = evaluate_receipt_policy(receipt, policy)
        prov_violations = [v for v in violations if v.rule == "require_provenance_repo"]
        self.assertTrue(prov_violations, "Expected require_provenance_repo violation")
        self.assertEqual(prov_violations[0].severity, "error")

    def test_require_schema_valid_warn_error(self):
        """require_schema_valid violation under warn must be severity=error."""
        from aiir._policy import evaluate_receipt_policy

        policy = {"require_schema_valid": True, "enforcement": "warn"}
        violations = evaluate_receipt_policy({}, policy, schema_errors=["some error"])
        schema_violations = [v for v in violations if v.rule == "require_schema_valid"]
        self.assertTrue(schema_violations)
        self.assertEqual(schema_violations[0].severity, "error")

    def test_no_require_no_violation(self):
        """When require_signing is not set, no violation even when unsigned."""
        from aiir._policy import evaluate_receipt_policy

        policy = {"require_signing": False, "enforcement": "hard-fail"}
        violations = evaluate_receipt_policy({}, policy, is_signed=False)
        signing_violations = [v for v in violations if v.rule == "require_signing"]
        self.assertEqual(signing_violations, [])


# ===========================================================================
# C5.5: _verify_release.py — enforcement validation fail-closed
# ===========================================================================


class TestEnforcementValidation(unittest.TestCase):
    """C5.5: Unknown enforcement value must raise ValueError (fail-closed)."""

    def _receipts_jsonl(self, tmpdir: str, receipts: List[Dict[str, Any]]) -> str:
        """Write receipts to a JSONL file and return the path."""
        p = Path(tmpdir) / "receipts.jsonl"
        lines = [json.dumps(r) for r in receipts]
        p.write_text("\n".join(lines), encoding="utf-8")
        return str(p)

    def test_known_enforcement_does_not_raise(self):
        """Valid enforcement values must not raise."""
        from aiir._verify_release import verify_release

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._receipts_jsonl(tmpdir, [r])
            for level in ("warn", "soft-fail", "hard-fail"):
                result = verify_release(
                    receipts_path=path,
                    policy_overrides={"enforcement": level},
                )
                # Just check it doesn't raise; result may pass or fail
                self.assertIn("verificationResult", result)

    def test_unknown_enforcement_raises(self):
        """Unknown enforcement string must raise ValueError (fail-closed)."""
        from aiir._verify_release import verify_release

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._receipts_jsonl(tmpdir, [r])
            with self.assertRaises(ValueError) as ctx:
                verify_release(
                    receipts_path=path,
                    policy_overrides={"enforcement": "super-strict"},
                )
            self.assertIn("Unknown enforcement", str(ctx.exception))

    def test_unknown_enforcement_error_names_value(self):
        """ValueError message must include the unknown enforcement value."""
        from aiir._verify_release import verify_release

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._receipts_jsonl(tmpdir, [r])
            with self.assertRaises(ValueError) as ctx:
                verify_release(
                    receipts_path=path,
                    policy_overrides={"enforcement": "typo-value"},
                )
            self.assertIn("typo-value", str(ctx.exception))


# ===========================================================================
# C5.6: depth guard in _verify_inference.py and _verify_research_evidence.py
# ===========================================================================


class TestInferenceDepthGuard(unittest.TestCase):
    """C5.6: Deep nesting in inference receipts returns valid:false, not RecursionError."""

    def _deep_nested(self, depth: int = 70) -> list:
        """Build a deeply nested list structure."""
        obj: Any = ["leaf"]
        for _ in range(depth):
            obj = [obj]
        return obj

    def test_deep_tokens_returns_valid_false(self):
        """Inference receipt with deeply nested tokens must return valid:false."""
        from aiir._verify_inference import verify_inference_receipt

        receipt = {
            "model_fingerprint": "a" * 64,
            "sampling_params": {"temperature": 0.7},
            "tokens": self._deep_nested(70),
            "granularity": "session",
            "hash": "0" * 64,
        }
        result = verify_inference_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("nested" in e.lower() for e in result["errors"]),
            f"Expected depth error, got: {result['errors']}",
        )

    def test_deep_sampling_params_returns_valid_false(self):
        """Deep nesting in sampling_params triggers the depth guard."""
        from aiir._verify_inference import verify_inference_receipt

        deep_params: Dict[str, Any] = {}
        current: Any = deep_params
        for i in range(70):
            child: Dict[str, Any] = {}
            current[f"k{i}"] = child
            current = child

        receipt = {
            "model_fingerprint": "a" * 64,
            "sampling_params": deep_params,
            "tokens": [1, 2, 3],
            "granularity": "session",
            "hash": "0" * 64,
        }
        result = verify_inference_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("nested" in e.lower() for e in result["errors"]),
            f"Expected depth error, got: {result['errors']}",
        )

    def test_normal_inference_receipt_unaffected(self):
        """A shallow inference receipt is unaffected by the depth guard."""
        from aiir._verify_inference import (
            _compute_inference_hash,
            verify_inference_receipt,
        )

        fp = "a" * 64
        sampling = {"temperature": 0.7, "top_p": 0.9}
        tokens = [1, 2, 3, 4, 5]
        granularity = "session"
        expected_hash = _compute_inference_hash(fp, sampling, tokens, granularity)
        receipt = {
            "model_fingerprint": fp,
            "sampling_params": sampling,
            "tokens": tokens,
            "granularity": granularity,
            "hash": expected_hash,
        }
        result = verify_inference_receipt(receipt)
        self.assertTrue(result["valid"], f"Unexpected errors: {result.get('errors')}")


class TestResearchEvidenceDepthGuard(unittest.TestCase):
    """C5.6: Deep nesting in research evidence receipts returns valid:false."""

    def test_deep_subject_returns_valid_false(self):
        """Deep nesting in the subject field triggers the depth guard."""
        from aiir._verify_research_evidence import verify_research_evidence_receipt

        r = _make_research_receipt()
        # Inject a deeply-nested dict into the subject
        deep: Dict[str, Any] = {}
        cur: Any = deep
        for i in range(70):
            child: Dict[str, Any] = {}
            cur[f"k{i}"] = child
            cur = child
        r["subject"]["deep"] = deep

        result = verify_research_evidence_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("nested" in e.lower() for e in result["errors"]),
            f"Expected depth error, got: {result['errors']}",
        )

    def test_normal_research_receipt_unaffected(self):
        """A valid shallow research evidence receipt is not rejected by the depth guard."""
        from aiir._verify_research_evidence import verify_research_evidence_receipt

        r = _make_research_receipt()
        result = verify_research_evidence_receipt(r)
        self.assertTrue(result["valid"], f"Unexpected errors: {result.get('errors')}")


# ===========================================================================
# R1: _verify.py — aiir.review_receipt verified by same hash mechanism
# ===========================================================================


class TestReviewReceiptVerification(unittest.TestCase):
    """R1: Review receipts must verify via the same content-hash mechanism."""

    def test_valid_review_receipt_passes(self):
        """A correctly-constructed review receipt must return valid=True."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt()
        result = verify_receipt(r)
        self.assertTrue(result["valid"], f"Expected valid=True, got: {result}")

    def test_valid_review_receipt_with_comment_passes(self):
        """A review receipt with a comment field must verify correctly."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt(include_comment=True)
        result = verify_receipt(r)
        self.assertTrue(result["valid"], f"Expected valid=True, got: {result}")

    def test_tampered_review_receipt_fails(self):
        """Tampering with a review receipt field must cause hash mismatch."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt()
        r["review_outcome"] = "rejected"  # Tamper
        result = verify_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any(
                "mismatch" in e.lower() or "hash" in e.lower() for e in result["errors"]
            ),
            f"Expected hash mismatch error, got: {result['errors']}",
        )

    def test_tampered_reviewer_email_fails(self):
        """Tampering with reviewer.email must fail verification."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt()
        r["reviewer"]["email"] = "attacker@evil.com"
        result = verify_receipt(r)
        self.assertFalse(result["valid"])

    def test_tampered_reviewed_commit_fails(self):
        """Tampering with the reviewed commit SHA must fail verification."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt()
        r["reviewed_commit"]["sha"] = "e" * 40
        result = verify_receipt(r)
        self.assertFalse(result["valid"])

    def test_unknown_type_still_rejected(self):
        """Unknown receipt types must still be rejected."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt()
        r["type"] = "aiir.mystery_receipt"
        result = verify_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("unknown receipt type" in e.lower() for e in result["errors"])
        )

    def test_commit_receipt_still_works(self):
        """The existing commit_receipt type must continue to verify normally."""
        from aiir._verify import verify_receipt

        r = _make_valid_commit_receipt()
        result = verify_receipt(r)
        self.assertTrue(result["valid"], f"Expected valid=True, got: {result}")

    def test_review_receipt_schema_prefix_check(self):
        """A review receipt with unknown schema prefix must be rejected."""
        from aiir._verify import verify_receipt

        r = _make_valid_review_receipt()
        r["schema"] = "other/review_receipt.v1"
        result = verify_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(any("schema" in e.lower() for e in result["errors"]))


# ===========================================================================
# Additional: \Z regex anchors — no trailing-newline bypass
# ===========================================================================


class TestRegexZAnchor(unittest.TestCase):
    """Additional finding: $ tolerates trailing newline; Z-anchor does not."""

    def test_version_with_trailing_newline_rejected(self):
        """A version string with a trailing newline must be rejected."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["version"] = "1.6.0\n"
        errors = validate_receipt_schema(r)
        version_errors = [e for e in errors if "version" in e.lower()]
        self.assertTrue(version_errors, f"Expected version error, got: {errors}")

    def test_receipt_id_with_trailing_newline_rejected(self):
        """A receipt_id with a trailing newline must be rejected."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["receipt_id"] = r["receipt_id"] + "\n"
        errors = validate_receipt_schema(r)
        id_errors = [e for e in errors if "receipt_id" in e.lower()]
        self.assertTrue(id_errors, f"Expected receipt_id error, got: {errors}")

    def test_content_hash_with_trailing_newline_rejected(self):
        """A content_hash with a trailing newline must be rejected."""
        from aiir._schema import validate_receipt_schema

        r = _make_valid_commit_receipt()
        r["content_hash"] = r["content_hash"] + "\n"
        errors = validate_receipt_schema(r)
        hash_errors = [e for e in errors if "content_hash" in e.lower()]
        self.assertTrue(hash_errors, f"Expected content_hash error, got: {errors}")

    def test_verify_version_with_trailing_newline_rejected(self):
        """_verify.py must also reject a version with trailing newline."""
        from aiir._verify import verify_receipt

        r = _make_valid_commit_receipt()
        # version is checked in verify_receipt
        r["version"] = "1.6.0\n"
        result = verify_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any("version" in e.lower() for e in result["errors"]),
            f"Expected version format error, got: {result['errors']}",
        )


# ===========================================================================
# Additional: array auto-detection robustness (mixed arrays)
# ===========================================================================


class TestArrayAutoDetection(unittest.TestCase):
    """Array auto-detection routes by the leading element but stays fail-closed.

    Detection keys off ``data[0]`` (so a chain with a bad entry is still routed
    to the chain verifier and reports per-entry errors); a misrouted mixed array
    therefore still fails verification rather than silently passing.
    """

    def test_mixed_array_routed_by_leader_still_fails_closed(self):
        """A mixed array whose leader looks like inference must still fail verification."""
        from aiir._verify import verify_receipt_file

        inference_r = {
            "model_fingerprint": "a" * 64,
            "sampling_params": {"temperature": 0.7},
            "tokens": [1, 2, 3],
            "granularity": "session",
            "hash": "0" * 64,
        }
        commit_r = _make_valid_commit_receipt()
        data = [inference_r, commit_r]

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "mixed.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            result = verify_receipt_file(str(p))
            # Routed to the chain verifier by the leader, but the non-conforming
            # commit-receipt entry makes the whole verification fail-closed.
            self.assertFalse(result["valid"])

    def test_pure_inference_array_still_routes_correctly(self):
        """A homogeneous inference array must still route to verify_inference_chain."""
        from aiir._verify import verify_receipt_file
        from aiir._verify_inference import _compute_inference_hash

        fp = "a" * 64
        sampling = {"temperature": 0.7}
        tokens = [1, 2, 3]
        granularity = "session"
        h = _compute_inference_hash(fp, sampling, tokens, granularity)
        r1 = {
            "model_fingerprint": fp,
            "sampling_params": sampling,
            "tokens": tokens,
            "granularity": granularity,
            "hash": h,
        }
        r2 = {
            "model_fingerprint": fp,
            "sampling_params": sampling,
            "tokens": [4, 5, 6],
            "granularity": granularity,
            "hash": _compute_inference_hash(fp, sampling, [4, 5, 6], granularity),
        }
        data = [r1, r2]

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "chain.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            result = verify_receipt_file(str(p))
            # Should be routed as inference chain
            self.assertIn(
                "valid_hashes", result, "Should be treated as inference chain"
            )


# ===========================================================================
# Additional: _evidence.py sigstore_claimed field
# ===========================================================================


class TestEvidenceSigstoreClaimed(unittest.TestCase):
    """Additional finding: evidence tier distinguishes claimed vs verified sigstore."""

    def test_embedded_sigstore_sets_claimed(self):
        """A receipt with embedded sigstore_bundle sets sigstore_claimed=True."""
        from aiir._evidence import _resolve_artifacts

        receipt = {
            "receipt_id": "g1-" + "a" * 32,
            "commit": {"sha": "a" * 40},
            "extensions": {"sigstore_bundle": "bundle-data"},
        }
        artifacts = _resolve_artifacts(receipt, {})
        self.assertTrue(
            artifacts.get("sigstore_claimed"), "sigstore_claimed should be True"
        )

    def test_no_sigstore_sets_claimed_false(self):
        """A receipt without any sigstore data sets sigstore_claimed=False."""
        from aiir._evidence import _resolve_artifacts

        receipt = {
            "receipt_id": "g1-" + "a" * 32,
            "commit": {"sha": "a" * 40},
            "extensions": {},
        }
        artifacts = _resolve_artifacts(receipt, {})
        self.assertFalse(
            artifacts.get("sigstore_claimed", False), "sigstore_claimed should be False"
        )

    def test_sidecar_presence_sets_sigstore_present_true(self):
        """An on-disk sidecar sets sigstore_present=True via artifact_index."""
        from aiir._evidence import _build_receipt_artifact_index, _resolve_artifacts

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / f"{r['receipt_id']}.json"
            receipt_path.write_text(json.dumps(r), encoding="utf-8")
            sidecar_path = Path(str(receipt_path) + ".sigstore")
            sidecar_path.write_text("{}", encoding="utf-8")

            index = _build_receipt_artifact_index(tmpdir)
            artifacts = _resolve_artifacts(r, index)
            self.assertTrue(
                artifacts.get("sigstore_present"),
                "sigstore_present should reflect sidecar",
            )


# ===========================================================================
# C5.2: _verify_release.py — evaluate_ledger_policy wired in
# ===========================================================================


class TestLedgerPolicyWired(unittest.TestCase):
    """C5.2: evaluate_ledger_policy is called from verify_release."""

    def _write_receipts(self, tmpdir: str, receipts: List[Dict[str, Any]]) -> str:
        p = Path(tmpdir) / "receipts.jsonl"
        lines = [json.dumps(r) for r in receipts]
        p.write_text("\n".join(lines), encoding="utf-8")
        return str(p)

    def test_max_ai_percent_violation_propagates(self):
        """When AI% exceeds max_ai_percent, verify_release must return FAILED."""
        from aiir._verify_release import verify_release

        # Build 1 AI receipt — AI% = 100%
        r = _make_valid_commit_receipt()
        r_ai = _make_valid_commit_receipt()
        # Override commit sha so they don't collide
        r_ai["commit"]["sha"] = "f" * 40
        # Re-hash with ai_authored=True
        core_ai = {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v1",
            "version": "1.6.0",
            "commit": {
                "sha": "f" * 40,
                "author": {
                    "name": "Bot",
                    "email": "bot@example.com",
                    "date": "2026-01-01T00:00:00Z",
                },
                "committer": {
                    "name": "Bot",
                    "email": "bot@example.com",
                    "date": "2026-01-01T00:00:00Z",
                },
                "subject": "ai commit",
                "message_hash": "sha256:" + _sha256("ai"),
                "diff_hash": "sha256:" + _sha256("aidiff"),
                "files_changed": 1,
                "files": ["ai.py"],
            },
            "ai_attestation": {
                "is_ai_authored": True,
                "signals_detected": ["ai-tool"],
                "signal_count": 1,
                "authorship_class": "ai_assisted",
                "detection_method": "heuristic_v2",
            },
            "provenance": {
                "repository": "https://github.com/example/repo",
                "tool": "https://github.com/invariant-systems-ai/aiir@1.6.0",
                "generator": "aiir.cli",
            },
        }
        cj = _canonical_json({k: core_ai[k] for k in _COMMIT_CORE_KEYS})
        ai_receipt = {
            **core_ai,
            "receipt_id": "g1-" + _sha256(cj)[:32],
            "content_hash": "sha256:" + _sha256(cj),
            "timestamp": "2026-01-01T00:00:00Z",
            "extensions": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_receipts(tmpdir, [ai_receipt])
            result = verify_release(
                receipts_path=path,
                policy_overrides={
                    "max_ai_percent": 10.0,  # AI% = 100%, limit = 10% => FAILED
                    "enforcement": "hard-fail",
                },
            )
            self.assertEqual(
                result["verificationResult"],
                "FAILED",
                f"Expected FAILED when AI% exceeds max_ai_percent, got: {result}",
            )

    def test_max_unsigned_receipts_violation_propagates(self):
        """When unsigned count exceeds max_unsigned_receipts, verify_release must fail."""
        from aiir._verify_release import verify_release

        r = _make_valid_commit_receipt()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_receipts(tmpdir, [r])
            result = verify_release(
                receipts_path=path,
                policy_overrides={
                    "max_unsigned_receipts": 0,  # 1 unsigned => FAILED
                    "enforcement": "hard-fail",
                },
            )
            self.assertEqual(
                result["verificationResult"],
                "FAILED",
                f"Expected FAILED when unsigned > max_unsigned_receipts, got: {result}",
            )


# ===========================================================================
# _verify_cbor.py: docstring update
# ===========================================================================


class TestCborDocstring(unittest.TestCase):
    """C2: decoder docstring must be updated."""

    def test_docstring_updated(self):
        """The decode_cbor docstring must mention RFC 8949 section 4.2.1."""
        from aiir._verify_cbor import decode_cbor

        doc = decode_cbor.__doc__ or ""
        self.assertIn("RFC 8949 section 4.2.1", doc)
        self.assertNotIn("encoded length then", doc)


if __name__ == "__main__":
    unittest.main()
