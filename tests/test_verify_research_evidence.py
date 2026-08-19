"""
Tests for research-evidence receipt verification.

Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import aiir.cli as cli
import aiir._verify_research_evidence as research_verify

from aiir._verify_research_evidence import (
    CONTRACT_VERSION,
    is_research_evidence_receipt,
    verify_research_evidence_receipt,
    verify_research_evidence_receipt_file,
    verify_research_evidence_receipt_set,
    _compute_research_evidence_hash,
)


def _make_receipt(*, claim_id="nisq-readiness-evidence-standard-2026-04-30"):
    subject = {
        "kind": "research_claim",
        "repo": "invariant-systems-research",
        "program_id": "02-nisq-readiness",
        "claim_id": claim_id,
        "title": "Evidence-first NISQ readiness standard",
    }
    claim = {
        "status": "verified",
        "summary": "Replayable NISQ evidence contract with IBM-backed statistical corpus.",
        "non_claims": [
            "not quantum advantage",
            "not fault tolerance",
        ],
        "last_reviewed": "2026-04-30",
    }
    evidence = {
        "artifacts": [
            {
                "type": "directory",
                "ref": "3-proof/3d-evidence/quantum/02-nisq-readiness/",
                "digest": "sha256:" + "1" * 64,
                "role": "evidence",
            }
        ],
        "verifiers": [
            {
                "type": "file",
                "ref": "3-proof/3p-deliverable/publications/arxiv/02-nisq-readiness/anc/verify_chsh.py",
                "digest": "sha256:" + "2" * 64,
                "role": "verifier",
            }
        ],
    }
    governance = {
        "public_safe": True,
        "ip_sensitive": False,
        "disclosure_tier": "public",
        "next_gate": "Internal publication signoff and DOI deposit using the capsule release checklist.",
    }
    proof = {
        "canonicalization": "aiir-canon-0",
    }
    timestamp = "2026-04-30T00:00:00Z"
    content_hash = _compute_research_evidence_hash(
        timestamp,
        subject,
        claim,
        evidence,
        governance,
        proof,
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "record_id": f"r1-{content_hash[:32]}",
        "timestamp": timestamp,
        "subject": subject,
        "claim": claim,
        "evidence": evidence,
        "governance": governance,
        "proof": {
            **proof,
            "content_hash": f"sha256:{content_hash}",
            "signature": None,
        },
        "extensions": {
            "io.invariantsystems.quantum": {
                "modality": "nisq",
            }
        },
    }


class TestIsResearchEvidenceReceipt(unittest.TestCase):
    def test_detects_valid_receipt(self):
        self.assertTrue(is_research_evidence_receipt(_make_receipt()))

    def test_rejects_non_matching_payload(self):
        self.assertFalse(is_research_evidence_receipt({"contract_version": "other/v1"}))
        self.assertFalse(is_research_evidence_receipt(None))


class TestVerifyResearchEvidenceReceipt(unittest.TestCase):
    def test_rejects_non_dict_receipt(self):
        result = verify_research_evidence_receipt("not-a-receipt")
        self.assertFalse(result["valid"])
        self.assertIn("receipt is not a dict", result["errors"])

    def test_rejects_wrong_contract_version(self):
        receipt = _make_receipt()
        receipt["contract_version"] = "other/v1"
        result = verify_research_evidence_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("contract_version must be", result["errors"][0])

    def test_valid_receipt(self):
        result = verify_research_evidence_receipt(_make_receipt())
        self.assertTrue(result["valid"])
        self.assertEqual(result["receipt_type"], "research_evidence_receipt")
        self.assertEqual(
            result["claim_id"], "nisq-readiness-evidence-standard-2026-04-30"
        )

    def test_tampered_hash(self):
        receipt = _make_receipt()
        receipt["proof"]["content_hash"] = "sha256:" + "0" * 64
        result = verify_research_evidence_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("content hash mismatch", result["errors"])

    def test_tampered_record_id(self):
        receipt = _make_receipt()
        receipt["record_id"] = "r1-" + "0" * 32
        result = verify_research_evidence_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("record_id mismatch", result["errors"])

    def test_invalid_structure(self):
        receipt = _make_receipt()
        receipt["subject"]["kind"] = "other"
        result = verify_research_evidence_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("subject.kind must be 'research_claim'", result["errors"])

    def test_reports_missing_top_level_fields(self):
        receipt = _make_receipt()
        receipt["timestamp"] = ""
        receipt["subject"] = []
        receipt["claim"] = None
        receipt["evidence"] = []
        receipt["governance"] = "bad"
        receipt["proof"] = []
        receipt["record_id"] = "bad"
        result = verify_research_evidence_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("missing or invalid timestamp", result["errors"])
        self.assertIn("missing or invalid subject", result["errors"])
        self.assertIn("missing or invalid claim", result["errors"])
        self.assertIn("missing or invalid evidence", result["errors"])
        self.assertIn("missing or invalid governance", result["errors"])
        self.assertIn("missing or invalid proof", result["errors"])
        self.assertIn("missing or invalid record_id", result["errors"])

    def test_reports_nested_field_validation_errors(self):
        receipt = _make_receipt()
        receipt["subject"]["title"] = ""
        receipt["claim"]["status"] = "unknown"
        receipt["claim"]["summary"] = ""
        receipt["claim"]["non_claims"] = ["ok", 5]
        receipt["claim"]["last_reviewed"] = ""
        receipt["governance"]["public_safe"] = "yes"
        receipt["governance"]["ip_sensitive"] = "no"
        receipt["governance"]["disclosure_tier"] = "secret"
        receipt["governance"]["next_gate"] = ""
        receipt["proof"]["canonicalization"] = "wrong"
        receipt["proof"]["content_hash"] = "bad"
        result = verify_research_evidence_receipt(receipt)
        self.assertFalse(result["valid"])
        self.assertIn("subject.title must be a non-empty string", result["errors"])
        self.assertTrue(
            any(
                err.startswith("claim.status must be one of")
                for err in result["errors"]
            )
        )
        self.assertIn("claim.summary must be a non-empty string", result["errors"])
        self.assertIn("claim.non_claims must be a list of strings", result["errors"])
        self.assertIn(
            "claim.last_reviewed must be a non-empty string", result["errors"]
        )
        self.assertIn("governance.public_safe must be a boolean", result["errors"])
        self.assertIn("governance.ip_sensitive must be a boolean", result["errors"])
        self.assertTrue(
            any(
                err.startswith("governance.disclosure_tier must be one of")
                for err in result["errors"]
            )
        )
        self.assertIn(
            "governance.next_gate must be a non-empty string", result["errors"]
        )
        self.assertIn("proof.canonicalization must be 'aiir-canon-0'", result["errors"])
        self.assertIn(
            "proof.content_hash must be 'sha256:' plus 64 hex chars", result["errors"]
        )

    def test_artifact_lists_require_list_object_and_keys(self):
        receipt = _make_receipt()
        receipt["evidence"]["artifacts"] = "bad"
        result = verify_research_evidence_receipt(receipt)
        self.assertIn("evidence.artifacts must be a list", result["errors"])

        receipt = _make_receipt()
        receipt["evidence"]["artifacts"] = [123]
        result = verify_research_evidence_receipt(receipt)
        self.assertIn("evidence.artifacts[0] must be an object", result["errors"])

        receipt = _make_receipt()
        receipt["evidence"]["verifiers"] = [{"type": "file", "ref": "x", "digest": ""}]
        result = verify_research_evidence_receipt(receipt)
        self.assertIn(
            "evidence.verifiers[0].digest must be a non-empty string",
            result["errors"],
        )

    def test_receipt_set(self):
        result = verify_research_evidence_receipt_set(
            [_make_receipt(), _make_receipt(claim_id="trace")]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["valid_receipts"], 2)

    def test_receipt_set_prefixes_invalid_receipt_errors(self):
        invalid = _make_receipt(claim_id="trace")
        invalid["record_id"] = "bad"
        result = verify_research_evidence_receipt_set([_make_receipt(), invalid])
        self.assertFalse(result["valid"])
        self.assertIn("receipt[1]: missing or invalid record_id", result["errors"])

    def test_receipt_set_rejects_oversized_input(self):
        with patch("aiir._verify_research_evidence.MAX_RECEIPTS_PER_RANGE", 1):
            result = verify_research_evidence_receipt_set(
                [_make_receipt(), _make_receipt(claim_id="trace")]
            )
        self.assertFalse(result["valid"])
        self.assertIn("receipt array too large", result["errors"][0])


class TestVerifyResearchEvidenceReceiptFile(unittest.TestCase):
    def test_valid_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(_make_receipt(), handle)
            handle.flush()
            result = verify_research_evidence_receipt_file(handle.name)
        os.unlink(handle.name)
        self.assertTrue(result["valid"])

    def test_file_not_found(self):
        result = verify_research_evidence_receipt_file(
            "/nonexistent/research-evidence.json"
        )
        self.assertFalse(result["valid"])

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            handle.write("not json")
            handle.flush()
            result = verify_research_evidence_receipt_file(handle.name)
        os.unlink(handle.name)
        self.assertFalse(result["valid"])

    def test_stat_failure(self):
        with (
            patch("aiir._verify_research_evidence.Path.exists", return_value=True),
            patch("aiir._verify_research_evidence.Path.is_symlink", return_value=False),
            patch(
                "aiir._verify_research_evidence.Path.stat", side_effect=OSError("boom")
            ),
        ):
            result = verify_research_evidence_receipt_file(
                "/tmp/research-evidence.json"
            )
        self.assertFalse(result["valid"])
        self.assertTrue(any("cannot stat file" in err for err in result["errors"]))

    def test_file_too_large(self):
        stat_result = type(
            "StatResult", (), {"st_size": research_verify.MAX_RECEIPT_FILE_SIZE + 1}
        )()
        with (
            patch("aiir._verify_research_evidence.Path.exists", return_value=True),
            patch("aiir._verify_research_evidence.Path.is_symlink", return_value=False),
            patch("aiir._verify_research_evidence.Path.stat", return_value=stat_result),
        ):
            result = verify_research_evidence_receipt_file(
                "/tmp/research-evidence.json"
            )
        self.assertFalse(result["valid"])
        self.assertIn("file too large", result["errors"][0])

    def test_set_envelope(self):
        payload = {"receipts": [_make_receipt(), _make_receipt(claim_id="trace")]}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(payload, handle)
            handle.flush()
            result = verify_research_evidence_receipt_file(handle.name)
        os.unlink(handle.name)
        self.assertTrue(result["valid"])
        self.assertEqual(result["total"], 2)

    def test_symlink_rejected(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(_make_receipt(), handle)
            handle.flush()
            link_path = handle.name + ".link"
            os.symlink(handle.name, link_path)
            result = verify_research_evidence_receipt_file(link_path)
        os.unlink(handle.name)
        os.unlink(link_path)
        self.assertFalse(result["valid"])

    def test_scalar_payload_rejected(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(5, handle)
            handle.flush()
            result = verify_research_evidence_receipt_file(handle.name)
        os.unlink(handle.name)
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"], ["expected JSON object or array"])


class TestAutoDetectionInVerifyFile(unittest.TestCase):
    def test_auto_detect_single(self):
        from aiir._verify import verify_receipt_file

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(_make_receipt(), handle)
            handle.flush()
            result = verify_receipt_file(handle.name)
        os.unlink(handle.name)
        self.assertTrue(result["valid"])
        self.assertEqual(result["receipt_type"], "research_evidence_receipt")

    def test_auto_detect_set(self):
        from aiir._verify import verify_receipt_file

        payload = [_make_receipt(), _make_receipt(claim_id="trace")]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(payload, handle)
            handle.flush()
            result = verify_receipt_file(handle.name)
        os.unlink(handle.name)
        self.assertTrue(result["valid"])
        self.assertEqual(result["valid_receipts"], 2)


class TestResearchEvidenceVerifyCli(unittest.TestCase):
    def _run_verify(self, payload):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as handle:
            json.dump(payload, handle)
            handle.flush()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
                rc = cli.main(["--verify", handle.name])
        os.unlink(handle.name)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_cli_verify_single_success(self):
        rc, stdout, stderr = self._run_verify(_make_receipt())
        self.assertEqual(rc, 0)
        self.assertIn("Research evidence receipt verified", stderr)
        self.assertIn('"receipt_type": "research_evidence_receipt"', stdout)

    def test_cli_verify_set_success(self):
        rc, stdout, stderr = self._run_verify(
            [_make_receipt(), _make_receipt(claim_id="trace")]
        )
        self.assertEqual(rc, 0)
        self.assertIn("Research evidence receipt set verified", stderr)
        self.assertIn('"valid_receipts": 2', stdout)

    def test_cli_verify_failure(self):
        receipt = _make_receipt()
        receipt["proof"]["content_hash"] = "sha256:" + "0" * 64
        rc, _stdout, stderr = self._run_verify(receipt)
        self.assertEqual(rc, 1)
        self.assertIn("Research evidence receipt verification failed", stderr)

    def test_cli_verify_set_failure(self):
        receipt = _make_receipt(claim_id="trace")
        receipt["record_id"] = "bad"
        rc, _stdout, stderr = self._run_verify([_make_receipt(), receipt])
        self.assertEqual(rc, 1)
        self.assertIn("Research evidence receipt set verification failed", stderr)
        self.assertIn("receipt[1]: missing or invalid record_id", stderr)


if __name__ == "__main__":
    unittest.main()
