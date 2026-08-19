"""Tests for evidence stream normalization and governance summaries."""
# Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aiir._evidence import (
    _as_receipt_list,
    _build_receipt_artifact_index,
    _get_agent_attestation,
    _get_editor_provenance,
    _resolve_artifacts,
    get_receipt_evidence_tier,
    import_evidence_stream,
    normalize_receipt_to_evidence,
    summarize_evidence_stream,
)


class TestEvidenceStream(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_receipt(
        self,
        sha: str,
        *,
        ai: bool = False,
        agent_tool: str | None = None,
        editor: bool = False,
        sigstore: bool = False,
        files: list[str] | None = None,
        model_vendor: str | None = None,
        model_family: str | None = None,
    ):
        receipt = {
            "type": "aiir.commit_receipt",
            "schema": "aiir/commit_receipt.v1",
            "version": "1.2.5",
            "receipt_id": f"g1-{sha[:16]}",
            "content_hash": f"sha256:{sha * 2}",
            "timestamp": "2026-03-15T12:00:00Z",
            "commit": {
                "sha": sha,
                "subject": f"Commit {sha[:8]}",
                "author": {"name": "Tester", "email": "tester@example.com"},
                "files": files or ["src/app.py"],
                "files_changed": len(files or ["src/app.py"]),
            },
            "ai_attestation": {
                "is_ai_authored": ai,
                "authorship_class": "ai_assisted" if ai else "human",
                "signals_detected": ["copilot"] if ai else [],
                "bot_signals_detected": [],
            },
            "extensions": {},
        }
        if agent_tool:
            receipt["extensions"]["agent_attestation"] = {
                "tool_id": agent_tool,
                "model_class": "gpt-5.4-mini",
            }
        if editor:
            receipt["extensions"]["editor_provenance"] = {
                "toolId": "aiir-vscode",
                "mode": "provable",
                "records": [
                    {
                        "id": "record-1",
                        "command": "generate",
                        "modelVendor": model_vendor or "openai",
                        "modelFamily": model_family or "gpt-5.4",
                        "files": [{"path": (files or ["src/app.py"])[0]}],
                    }
                ],
            }
        if sigstore:
            receipt["extensions"]["sigstore_bundle"] = {"mediaType": "application/json"}
        return receipt

    def test_as_receipt_list_supports_supported_inputs(self):
        receipt = self._make_receipt("a" * 40)
        self.assertEqual(_as_receipt_list([receipt]), [receipt])
        self.assertEqual(_as_receipt_list({"receipts": [receipt]}), [receipt])
        self.assertEqual(_as_receipt_list(receipt), [receipt])
        self.assertEqual(_as_receipt_list({"foo": "bar"}), [])
        self.assertEqual(_as_receipt_list("bad input"), [])

    def test_receipt_tier_classification_covers_all_public_tiers(self):
        unsigned = self._make_receipt("b" * 40)
        heuristic = self._make_receipt("c" * 40, ai=True)
        provable = self._make_receipt("d" * 40, editor=True)
        signed = self._make_receipt("e" * 40, editor=True, sigstore=True)

        self.assertEqual(get_receipt_evidence_tier(unsigned), "unsigned")
        self.assertEqual(get_receipt_evidence_tier(heuristic), "heuristic")
        self.assertEqual(get_receipt_evidence_tier(provable), "provable")
        self.assertEqual(
            get_receipt_evidence_tier(signed, sigstore_present=True), "signed"
        )

    def test_receipt_artifact_index_reads_receipt_dir_and_skips_bad_json(self):
        receipts_dir = Path(self.tmpdir, ".receipts")
        receipts_dir.mkdir(parents=True)
        receipt = self._make_receipt("f" * 40)
        receipt_path = receipts_dir / "receipt_ffffffffffff_deadbeefdeadbeef.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_path.with_suffix(".cbor").write_bytes(b"cbor")
        Path(str(receipt_path) + ".sigstore").write_text("{}", encoding="utf-8")
        (receipts_dir / "receipt_broken.json").write_text("{", encoding="utf-8")
        (receipts_dir / "receipt_empty_keys.json").write_text(
            json.dumps({"receipt_id": "", "content_hash": "", "commit": {"sha": ""}}),
            encoding="utf-8",
        )

        artifact_index = _build_receipt_artifact_index(str(receipts_dir))
        self.assertEqual(
            artifact_index[receipt["receipt_id"]]["artifact_source"], "receipt-dir"
        )
        self.assertTrue(artifact_index[receipt["receipt_id"]]["cbor_present"])
        self.assertTrue(artifact_index[receipt["receipt_id"]]["sigstore_present"])
        self.assertEqual(_build_receipt_artifact_index(None), {})
        self.assertEqual(
            _build_receipt_artifact_index(str(receipts_dir / "missing")), {}
        )

    def test_receipt_artifact_index_accepts_non_prefixed_json_receipts(self):
        receipts_dir = Path(self.tmpdir, ".receipts")
        receipts_dir.mkdir(parents=True)
        receipt = self._make_receipt("1" * 40)
        receipt_path = receipts_dir / "receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        Path(str(receipt_path) + ".sigstore").write_text("{}", encoding="utf-8")
        (receipts_dir / "attestation.json").write_text("[]", encoding="utf-8")

        artifact_index = _build_receipt_artifact_index(str(receipts_dir))

        self.assertTrue(artifact_index[receipt["receipt_id"]]["sigstore_present"])
        self.assertTrue(
            Path(artifact_index[receipt["receipt_id"]]["json_path"]).samefile(
                receipt_path
            )
        )

    def test_attestation_helpers_handle_missing_and_invalid_extensions(self):
        receipt = self._make_receipt("1" * 40, agent_tool="copilot", editor=True)
        self.assertEqual(_get_agent_attestation(receipt)["tool_id"], "copilot")
        self.assertEqual(_get_editor_provenance(receipt)["toolId"], "aiir-vscode")

        receipt["extensions"]["agent_attestation"] = []
        receipt["extensions"]["editor_provenance"] = []
        self.assertEqual(_get_agent_attestation(receipt), {})
        self.assertEqual(_get_editor_provenance(receipt), {})

    def test_resolve_artifacts_prefers_receipt_dir_over_embedded_defaults(self):
        receipt = self._make_receipt("2" * 40, sigstore=True)
        resolved = _resolve_artifacts(receipt, {})
        self.assertEqual(resolved["artifact_source"], "embedded")
        self.assertTrue(resolved["sigstore_present"])
        self.assertFalse(resolved["cbor_present"])

        artifact_index = {
            receipt["receipt_id"]: {
                "cbor_present": True,
                "sigstore_present": False,
                "artifact_source": "receipt-dir",
                "json_path": "/tmp/receipt.json",
            }
        }
        resolved = _resolve_artifacts(receipt, artifact_index)
        self.assertEqual(resolved["artifact_source"], "receipt-dir")
        self.assertTrue(resolved["cbor_present"])
        self.assertFalse(resolved["sigstore_present"])

    def test_normalize_receipt_to_evidence_flattens_tool_and_upgrade_fields(self):
        receipt = self._make_receipt(
            "3" * 40,
            ai=True,
            agent_tool="copilot",
            editor=True,
            files=["src/hot.py", "src/other.py"],
        )
        event = normalize_receipt_to_evidence(receipt)
        self.assertEqual(event["evidence_tier"], "provable")
        self.assertEqual(event["upgrade_needed"], "sign-in-ci")
        self.assertEqual(event["attested_system"], "aiir-vscode via openai gpt-5.4")
        self.assertEqual(event["files_changed"], 2)
        self.assertEqual(event["editor_record_count"], 1)

        model_only = self._make_receipt("4" * 40)
        model_only["extensions"]["agent_attestation"] = {"model_class": "gpt-5.4"}
        model_event = normalize_receipt_to_evidence(model_only)
        self.assertEqual(model_event["attested_system"], "gpt-5.4")

        plain_event = normalize_receipt_to_evidence(
            self._make_receipt("5" * 40, files=[])
        )
        self.assertEqual(plain_event["attested_system"], "No explicit tool attested")
        self.assertEqual(plain_event["upgrade_needed"], "add-provenance-and-sign")

    def test_import_evidence_stream_accepts_bundle_and_enriches_from_receipt_dir(self):
        receipt = self._make_receipt("6" * 40, ai=True)
        receipts_dir = Path(self.tmpdir, ".receipts")
        receipts_dir.mkdir(parents=True)
        receipt_path = receipts_dir / "receipt_666666666666_feedfeedfeedfeed.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        receipt_path.with_suffix(".cbor").write_bytes(b"cbor")

        stream = import_evidence_stream(
            {"format": "aiir.export.v1", "receipts": [receipt]}, str(receipts_dir)
        )
        self.assertEqual(stream["format"], "aiir.evidence_stream.v1")
        self.assertEqual(stream["source_format"], "aiir.export.v1")
        self.assertEqual(stream["events"][0]["artifact_source"], "receipt-dir")
        self.assertTrue(stream["events"][0]["cbor_present"])

        list_stream = import_evidence_stream([receipt])
        self.assertEqual(list_stream["source_format"], "receipts")

    def test_summarize_evidence_stream_produces_governance_outputs(self):
        heuristic = self._make_receipt("7" * 40, ai=True, files=["src/hot.py"])
        provable = self._make_receipt(
            "8" * 40, ai=True, editor=True, files=["src/hot.py", "src/side.py"]
        )
        signed = self._make_receipt(
            "9" * 40, ai=True, editor=True, sigstore=True, files=["src/release.py"]
        )

        stream = import_evidence_stream({"receipts": [heuristic, provable, signed]})
        stream["events"].append("ignore me")
        stream["events"].append(
            {
                "evidence_tier": "mystery",
                "timestamp": "2026-03-15T12:30:00Z",
                "ai_authored": True,
                "ai_signals": ["copilot"],
                "files": ["", None],
                "attested_system": "No explicit tool attested",
                "release_proof_ready": False,
            }
        )
        summary = summarize_evidence_stream(stream)

        self.assertEqual(summary["format"], "aiir.evidence_summary.v1")
        self.assertEqual(summary["total_receipts"], 4)
        self.assertEqual(summary["ai_receipts"], 4)
        self.assertEqual(summary["evidence_tiers"]["heuristic"], 1)
        self.assertEqual(summary["evidence_tiers"]["provable"], 1)
        self.assertEqual(summary["evidence_tiers"]["signed"], 1)
        self.assertEqual(summary["evidence_tiers"]["unsigned"], 1)
        self.assertEqual(summary["unsigned_risk"]["heuristic_only"], 1)
        self.assertEqual(summary["unsigned_risk"]["provable_but_unsigned"], 1)
        self.assertEqual(summary["unsigned_risk"]["ai_receipts_without_signing"], 3)
        self.assertEqual(summary["release_proof_readiness"]["status"], "partial")
        self.assertEqual(summary["release_proof_readiness"]["ready_receipts"], 1)
        self.assertEqual(summary["hot_path_ai_changes"][0]["path"], "src/hot.py")
        self.assertEqual(
            summary["top_ai_systems"][0]["system"], "aiir-vscode via openai gpt-5.4"
        )
        self.assertEqual(summary["ai_coverage_trend"][0]["date"], "2026-03-15")
        self.assertGreater(summary["ai_coverage_trend"][0]["ai_percentage"], 0)

    def test_summarize_evidence_stream_handles_empty_stream(self):
        summary = summarize_evidence_stream({"events": []})
        self.assertEqual(summary["total_receipts"], 0)
        self.assertEqual(summary["release_proof_readiness"]["status"], "unsigned")
        self.assertEqual(summary["hot_path_ai_changes"], [])
        self.assertEqual(summary["top_ai_systems"], [])
