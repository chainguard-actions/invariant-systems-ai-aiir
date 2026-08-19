# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Tests for the standalone agent-receipt profile (aiir/agent_receipt.v0.1).

Phase 1: the core build + verify module. Validates byte-exact conformance with
the published v0.1 test vectors and exercises every branch of the module.
"""

import json
import unittest
from pathlib import Path

from aiir._agent_receipt import (
    AGENT_RECEIPT_CONTRACT_VERSION,
    AGENT_RECEIPT_ID_PREFIX,
    build_agent_receipt,
    format_agent_receipt_pretty,
    is_agent_receipt,
    verify_agent_receipt,
)
from aiir._core import _canonical_json, _sha256

_VECTORS_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "test-vectors"
    / "agent_receipt_vectors.v0.1.json"
)


def _build_from_core(core: dict) -> dict:
    """Drive build_agent_receipt from a vector's input_core dict."""
    actor = core["actor"]
    action = core["action"]
    artifacts = core["artifacts"]
    policy = core["policy"]
    return build_agent_receipt(
        actor_kind=actor["kind"],
        actor_tool_name=actor["tool"]["name"],
        actor_tool_surface=actor["tool"].get("surface"),
        actor_session_ref=actor.get("session_ref"),
        action_kind=action["kind"],
        action_intent=action.get("intent"),
        action_summary=action.get("summary"),
        artifact_inputs=artifacts.get("inputs"),
        artifact_outputs=artifacts.get("outputs"),
        policy_decision=policy["decision"],
        policy_reasons=policy.get("reasons"),
        policy_contract_ref=policy.get("contract_ref"),
        timestamp=core["timestamp"],
    )


class TestAgentReceiptVectors(unittest.TestCase):
    """Byte-exact conformance with the published v0.1 vectors."""

    def setUp(self):
        self.data = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))
        self.vectors = self.data["vectors"]

    def test_three_vectors_present(self):
        self.assertEqual(len(self.vectors), 3)

    def test_each_vector_reproduces_byte_exact(self):
        for vec in self.vectors:
            with self.subTest(vector=vec["id"]):
                core = vec["input_core"]
                exp = vec["expected"]
                receipt = _build_from_core(core)
                # record_id and content_hash match the published expectation
                self.assertEqual(receipt["record_id"], exp["record_id"])
                self.assertEqual(receipt["proof"]["content_hash"], exp["content_hash"])
                # the canonical core reproduces byte-exact
                rebuilt_core = {
                    "contract_version": receipt["contract_version"],
                    "timestamp": receipt["timestamp"],
                    "actor": receipt["actor"],
                    "action": receipt["action"],
                    "artifacts": receipt["artifacts"],
                    "policy": receipt["policy"],
                    "proof": {"canonicalization": "aiir-canon-0"},
                }
                self.assertEqual(_canonical_json(rebuilt_core), exp["canonical_json"])
                self.assertEqual(
                    "sha256:" + _sha256(exp["canonical_json"]), exp["content_hash"]
                )

    def test_each_vector_verifies_valid(self):
        for vec in self.vectors:
            with self.subTest(vector=vec["id"]):
                receipt = _build_from_core(vec["input_core"])
                result = verify_agent_receipt(receipt)
                self.assertTrue(result["valid"])
                self.assertEqual(result["record_id"], vec["expected"]["record_id"])
                self.assertEqual(
                    result["expected_content_hash"], vec["expected"]["content_hash"]
                )


class TestIsAgentReceipt(unittest.TestCase):
    def test_true_for_agent_receipt(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="claude-code", action_kind="edit"
        )
        self.assertTrue(is_agent_receipt(r))

    def test_false_for_non_dict(self):
        self.assertFalse(is_agent_receipt("nope"))
        self.assertFalse(is_agent_receipt(None))

    def test_false_for_wrong_contract_version(self):
        self.assertFalse(
            is_agent_receipt({"contract_version": "aiir/commit_receipt.v2"})
        )
        self.assertFalse(is_agent_receipt({}))


class TestBuildOptionalFields(unittest.TestCase):
    def test_minimal_receipt_omits_optional_fields(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="claude-code", action_kind="run"
        )
        self.assertEqual(r["contract_version"], AGENT_RECEIPT_CONTRACT_VERSION)
        self.assertTrue(r["record_id"].startswith(AGENT_RECEIPT_ID_PREFIX))
        self.assertNotIn("surface", r["actor"]["tool"])
        self.assertNotIn("session_ref", r["actor"])
        self.assertNotIn("intent", r["action"])
        self.assertNotIn("summary", r["action"])
        self.assertEqual(r["artifacts"], {"inputs": [], "outputs": []})
        self.assertEqual(r["policy"], {"decision": "not_evaluated"})
        self.assertNotIn("extensions", r)
        # auto timestamp present
        self.assertTrue(r["timestamp"])
        self.assertIsNone(r["proof"]["signature"])

    def test_all_optional_fields_included(self):
        r = build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="cursor",
            actor_tool_surface="ide",
            actor_session_ref="sess_9",
            action_kind="edit",
            action_intent="apply_patch",
            action_summary="did a thing",
            artifact_inputs=[{"type": "file", "ref": "a.py", "role": "source"}],
            artifact_outputs=[{"type": "file", "ref": "a.py"}],
            policy_decision="allowed",
            policy_reasons=["ok"],
            policy_contract_ref="aiir://policy/x",
            extensions={"run_id": "123", 5: "ignored-non-str-key", "blank": ""},
        )
        self.assertEqual(r["actor"]["tool"]["surface"], "ide")
        self.assertEqual(r["actor"]["session_ref"], "sess_9")
        self.assertEqual(r["action"]["intent"], "apply_patch")
        self.assertEqual(r["policy"]["reasons"], ["ok"])
        self.assertEqual(r["policy"]["contract_ref"], "aiir://policy/x")
        self.assertNotIn("role", r["artifacts"]["outputs"][0])
        self.assertEqual(r["extensions"], {"run_id": "123", "blank": ""})
        self.assertTrue(verify_agent_receipt(r)["valid"])

    def test_empty_extensions_block_omitted(self):
        r = build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="t",
            action_kind="run",
            extensions={},
        )
        self.assertNotIn("extensions", r)

    def test_non_dict_extensions_sanitized_to_empty(self):
        # A truthy non-dict extensions value is reduced to an empty block.
        r = build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="t",
            action_kind="run",
            extensions=["not", "a", "dict"],  # type: ignore[arg-type]
        )
        self.assertEqual(r["extensions"], {})

    def test_extensions_drops_escape_only_keys(self):
        r = build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="t",
            action_kind="run",
            extensions={"\x1b[0m": "x", "keep": "y"},
        )
        self.assertEqual(r["extensions"], {"keep": "y"})


class TestVerifyMalformedCore(unittest.TestCase):
    """verify must fail-closed (not crash) on every malformed sub-object."""

    def _valid(self):
        return build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="claude-code",
            action_kind="edit",
            artifact_inputs=[{"type": "file", "ref": "a.py"}],
            policy_reasons=["ok"],
        )

    def _assert_invalid(self, mutate):
        # Fail-closed is the guarantee: a structural problem yields errors; a
        # field that normalizes cleanly but changes the core yields a clean hash
        # mismatch (valid=False, no errors). Both must be rejected.
        r = self._valid()
        mutate(r)
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])

    def test_actor_tool_not_object(self):
        self._assert_invalid(lambda r: r["actor"].__setitem__("tool", "x"))

    def test_action_not_object(self):
        self._assert_invalid(lambda r: r.__setitem__("action", "x"))

    def test_artifacts_missing_defaults_then_mismatches(self):
        # Removing artifacts hits the None->{} default path; the recomputed
        # hash then no longer matches the stored one (fail-closed).
        self._assert_invalid(lambda r: r.pop("artifacts"))

    def test_artifacts_not_object(self):
        self._assert_invalid(lambda r: r.__setitem__("artifacts", "x"))

    def test_artifacts_side_not_array(self):
        self._assert_invalid(lambda r: r.__setitem__("artifacts", {"inputs": "x"}))

    def test_policy_missing_defaults_then_mismatches(self):
        self._assert_invalid(lambda r: r.pop("policy"))

    def test_policy_not_object(self):
        self._assert_invalid(lambda r: r.__setitem__("policy", "x"))

    def test_policy_reasons_not_array(self):
        self._assert_invalid(
            lambda r: r.__setitem__("policy", {"decision": "allowed", "reasons": "x"})
        )


class TestBuildValidation(unittest.TestCase):
    def test_empty_required_string_rejected(self):
        with self.assertRaises(ValueError):
            build_agent_receipt(actor_kind="", actor_tool_name="t", action_kind="run")

    def test_non_string_required_rejected(self):
        with self.assertRaises(ValueError):
            build_agent_receipt(
                actor_kind="agent",
                actor_tool_name=123,
                action_kind="run",  # type: ignore[arg-type]
            )

    def test_artifact_entry_must_be_object(self):
        with self.assertRaises(ValueError):
            build_agent_receipt(
                actor_kind="agent",
                actor_tool_name="t",
                action_kind="edit",
                artifact_inputs=["not-an-object"],  # type: ignore[list-item]
            )

    def test_artifact_entry_requires_type_and_ref(self):
        with self.assertRaises(ValueError):
            build_agent_receipt(
                actor_kind="agent",
                actor_tool_name="t",
                action_kind="edit",
                artifact_outputs=[{"type": "file"}],  # missing ref
            )

    def test_too_many_reasons_rejected(self):
        with self.assertRaises(ValueError):
            build_agent_receipt(
                actor_kind="agent",
                actor_tool_name="t",
                action_kind="run",
                policy_reasons=[f"r{i}" for i in range(51)],
            )

    def test_too_many_artifacts_rejected(self):
        with self.assertRaises(ValueError):
            build_agent_receipt(
                actor_kind="agent",
                actor_tool_name="t",
                action_kind="run",
                artifact_inputs=[{"type": "file", "ref": str(i)} for i in range(201)],
            )

    def test_terminal_escapes_stripped(self):
        r = build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="cla\x1b[31mude",
            action_kind="run",
        )
        self.assertEqual(r["actor"]["tool"]["name"], "claude")


class TestVerifyAgentReceipt(unittest.TestCase):
    def _valid(self):
        return build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="claude-code",
            action_kind="edit",
            action_summary="x",
            artifact_outputs=[{"type": "file", "ref": "a.py", "role": "source"}],
            policy_decision="allowed",
            policy_reasons=["ok"],
        )

    def test_valid_round_trip(self):
        r = self._valid()
        result = verify_agent_receipt(r)
        self.assertTrue(result["valid"])
        self.assertTrue(result["content_hash_match"])
        self.assertTrue(result["record_id_match"])
        self.assertEqual(result["actor_tool"], "claude-code")
        self.assertEqual(result["action_kind"], "edit")
        self.assertEqual(result["policy_decision"], "allowed")

    def test_non_dict_receipt(self):
        result = verify_agent_receipt("nope")  # type: ignore[arg-type]
        self.assertFalse(result["valid"])
        self.assertIn("not a JSON object", result["errors"][0])

    def test_wrong_contract_version(self):
        r = self._valid()
        r["contract_version"] = "aiir/agent_receipt.v9.9"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])

    def test_proof_not_object(self):
        r = self._valid()
        r["proof"] = "nope"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(any("proof must be" in e for e in result["errors"]))

    def test_malformed_core_returns_invalid(self):
        r = self._valid()
        r["actor"] = "not-an-object"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertTrue(result["errors"])

    def test_tampered_field_fails_and_no_oracle(self):
        r = self._valid()
        r["action"]["summary"] = "tampered"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        # No forgery oracle: the recomputed hash is not exposed on failure.
        self.assertNotIn("expected_content_hash", result)
        self.assertNotIn("expected_record_id", result)

    def test_tampered_record_id_fails(self):
        r = self._valid()
        r["record_id"] = "a1-" + "0" * 32
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertFalse(result["record_id_match"])


class TestVerifyD2CanonicalFormRejection(unittest.TestCase):
    """D2 security tests: verify must reject receipts whose stored string fields
    are not in canonical form (strip_terminal_escapes(x)[:cap] != x).

    These are the three proven exploit classes:
      1. escape-only collision — a field containing ANSI escape sequences that
         normalise back to the original value, making the hash match the clean
         receipt even though the field is dirty.
      2. control-byte injection — a field containing raw C0/C1 control bytes
         (e.g. 0x01) that are stripped during normalisation, leaving the same
         post-clean value as the original.
      3. truncation + trailing bytes — a field whose length exceeds the cap but
         whose prefix (after truncation) equals the original canonical value,
         meaning the trailing garbage normalises away.

    Each exploit was confirmed to return valid:True BEFORE the fix and must
    return valid:False AFTER it.
    """

    def _base_receipt(self, **kwargs):
        return build_agent_receipt(
            actor_kind="agent",
            actor_tool_name="claude-code",
            action_kind="edit",
            policy_decision="allowed",
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Exploit 1: escape-only collision
    # ------------------------------------------------------------------

    def test_escape_only_collision_actor_tool_name(self):
        """actor.tool.name with embedded ANSI escape stripped to same value."""
        r = self._base_receipt()
        r["actor"] = dict(r["actor"])
        r["actor"]["tool"] = dict(r["actor"]["tool"])
        r["actor"]["tool"]["name"] = "cla\x1b[31mude-code"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_escape_only_collision_action_kind(self):
        """action.kind with OSC escape that normalises to the clean value."""
        r = self._base_receipt()
        r["action"] = dict(r["action"])
        r["action"]["kind"] = "ed\x1b]0;evil\x07it"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_escape_only_collision_policy_decision(self):
        """policy.decision with embedded CSI escape."""
        r = self._base_receipt()
        r["policy"] = dict(r["policy"])
        r["policy"]["decision"] = "allow\x1b[0med"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    # ------------------------------------------------------------------
    # Exploit 2: control-byte injection
    # ------------------------------------------------------------------

    def test_control_byte_injection_actor_kind(self):
        """actor.kind with embedded NUL/SOH control byte stripped to same."""
        r = self._base_receipt()
        r["actor"] = dict(r["actor"])
        r["actor"]["kind"] = "age\x00nt"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_control_byte_injection_action_kind(self):
        """action.kind with raw SOH control byte stripped away."""
        r = self._base_receipt()
        r["action"] = dict(r["action"])
        r["action"]["kind"] = "edi\x01t"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_control_byte_injection_artifact_ref(self):
        """artifact ref with embedded DEL (0x7F) control byte."""
        r = self._base_receipt(
            artifact_inputs=[{"type": "file", "ref": "a.py"}],
        )
        r["artifacts"] = {
            "inputs": [{"type": "file", "ref": "a.\x7fpy"}],
            "outputs": [],
        }
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_control_byte_injection_policy_reason(self):
        """policy.reasons entry with 8-bit C1 control (0x9B = CSI)."""
        r = self._base_receipt(policy_reasons=["ok"])
        r["policy"] = dict(r["policy"])
        r["policy"]["reasons"] = [
            "o\x9bk"
        ]  # 8-bit CSI stripped by _strip_terminal_escapes
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    # ------------------------------------------------------------------
    # Exploit 3: truncation + trailing bytes
    # ------------------------------------------------------------------

    def test_truncation_plus_trailing_control_byte_summary(self):
        """action.summary at exactly 2000 chars + trailing control: prefix matches."""
        r = self._base_receipt(action_summary="a" * 2000)
        r["action"] = dict(r["action"])
        r["action"]["summary"] = "a" * 2000 + "\x01"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_truncation_plus_trailing_escape_summary(self):
        """action.summary at exactly 2000 chars + trailing ANSI escape."""
        r = self._base_receipt(action_summary="a" * 2000)
        r["action"] = dict(r["action"])
        r["action"]["summary"] = "a" * 2000 + "\x1b[0m"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_truncation_plus_trailing_control_byte_intent(self):
        """action.intent at exactly 200 chars + trailing control byte."""
        r = self._base_receipt(action_intent="b" * 200)
        r["action"] = dict(r["action"])
        r["action"]["intent"] = "b" * 200 + "\x01"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    def test_truncation_plus_trailing_control_byte_timestamp(self):
        """timestamp at exactly 64 chars + trailing control byte."""
        import json
        from pathlib import Path

        vectors_path = (
            Path(__file__).resolve().parent.parent
            / "schemas"
            / "test-vectors"
            / "agent_receipt_vectors.v0.1.json"
        )
        data = json.loads(vectors_path.read_text(encoding="utf-8"))
        vec = data["vectors"][0]
        r = build_agent_receipt(
            actor_kind=vec["input_core"]["actor"]["kind"],
            actor_tool_name=vec["input_core"]["actor"]["tool"]["name"],
            action_kind=vec["input_core"]["action"]["kind"],
            timestamp=vec["input_core"]["timestamp"],
        )
        # inject truncation+trailing on timestamp (cap=64)
        r["timestamp"] = r["timestamp"] + "\x01"
        result = verify_agent_receipt(r)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["receipt fields are not in canonical form"])

    # ------------------------------------------------------------------
    # Regression: clean receipts still verify and 3 published vectors verify
    # ------------------------------------------------------------------

    def test_clean_receipt_still_verifies(self):
        """A normally-built receipt must still verify as valid after the fix."""
        r = self._base_receipt(
            action_summary="legitimate summary",
            action_intent="apply_patch",
            actor_tool_surface="ide",
            actor_session_ref="sess_99",
            artifact_inputs=[{"type": "file", "ref": "src/a.py", "role": "source"}],
            artifact_outputs=[{"type": "file", "ref": "src/a.py"}],
            policy_reasons=["workspace_loaded"],
            policy_contract_ref="aiir://policy/default",
        )
        result = verify_agent_receipt(r)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_three_published_vectors_still_verify(self):
        """All three published v0.1 test vectors must still verify after the fix."""
        import json
        from pathlib import Path

        vectors_path = (
            Path(__file__).resolve().parent.parent
            / "schemas"
            / "test-vectors"
            / "agent_receipt_vectors.v0.1.json"
        )
        data = json.loads(vectors_path.read_text(encoding="utf-8"))
        vectors = data["vectors"]
        self.assertEqual(len(vectors), 3)
        for vec in vectors:
            with self.subTest(vector=vec["id"]):
                core = vec["input_core"]
                actor = core["actor"]
                action = core["action"]
                artifacts = core["artifacts"]
                policy = core["policy"]
                receipt = build_agent_receipt(
                    actor_kind=actor["kind"],
                    actor_tool_name=actor["tool"]["name"],
                    actor_tool_surface=actor["tool"].get("surface"),
                    actor_session_ref=actor.get("session_ref"),
                    action_kind=action["kind"],
                    action_intent=action.get("intent"),
                    action_summary=action.get("summary"),
                    artifact_inputs=artifacts.get("inputs"),
                    artifact_outputs=artifacts.get("outputs"),
                    policy_decision=policy["decision"],
                    policy_reasons=policy.get("reasons"),
                    policy_contract_ref=policy.get("contract_ref"),
                    timestamp=core["timestamp"],
                )
                result = verify_agent_receipt(receipt)
                self.assertTrue(result["valid"], f"Vector {vec['id']} failed: {result}")
                self.assertEqual(result["errors"], [])


class TestFormatPretty(unittest.TestCase):
    def test_pretty_on_valid_receipt(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="claude-code", action_kind="edit"
        )
        text = format_agent_receipt_pretty(r)
        self.assertIn("Agent receipt a1-", text)
        self.assertIn("claude-code", text)
        self.assertIn("edit", text)

    def test_pretty_tolerates_malformed_receipt(self):
        # Non-dict sub-objects must not crash the formatter.
        text = format_agent_receipt_pretty(
            {"record_id": "a1-x", "actor": "bad", "action": None, "policy": 5}
        )
        self.assertIn("a1-x", text)


if __name__ == "__main__":
    unittest.main()
