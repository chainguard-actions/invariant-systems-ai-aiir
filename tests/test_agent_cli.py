# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""CLI + routing integration for agent receipts (Phase 2).

Covers `aiir agent emit|verify`, the `aiir verify` routing, and ledger/append
routing for the aiir/agent_receipt.v0.1 profile.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from aiir._agent_receipt import build_agent_receipt
from aiir._ledger import append_to_ledger
from aiir._verify import verify_receipt, verify_receipt_file
from aiir.cli import _parse_agent_artifact, main


@contextlib.contextmanager
def _in_dir(path):
    """chdir into ``path`` for the duration of the block (ledger must be in cwd)."""
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _read_ledger(ledger_dir):
    """Read receipts from a ledger's receipts.jsonl (one JSON object per line)."""
    path = Path(ledger_dir) / "receipts.jsonl"
    text = path.read_text(encoding="utf-8").strip()
    return [json.loads(line) for line in text.splitlines() if line]


def _run(argv):
    """Run the CLI, returning (exit_code, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    return code, out.getvalue()


class TestParseAgentArtifact(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(
            _parse_agent_artifact("file:src/app.py"),
            {"type": "file", "ref": "src/app.py"},
        )

    def test_ref_may_contain_colons(self):
        self.assertEqual(
            _parse_agent_artifact("test:tests/x.py::test_y"),
            {"type": "test", "ref": "tests/x.py::test_y"},
        )

    def test_missing_separator_rejected(self):
        with self.assertRaises(ValueError):
            _parse_agent_artifact("noseparator")

    def test_empty_type_rejected(self):
        with self.assertRaises(ValueError):
            _parse_agent_artifact(":ref")


class TestAgentEmit(unittest.TestCase):
    def test_emit_json_to_stdout(self):
        code, out = _run(
            [
                "agent",
                "emit",
                "--action",
                "edit",
                "--tool",
                "claude-code",
                "--kind",
                "agent",
                "--surface",
                "cli",
                "--session",
                "s1",
                "--intent",
                "apply_patch",
                "--summary",
                "did a thing",
                "--input",
                "file:a.py",
                "--output",
                "file:a.py",
                "--policy",
                "allowed",
                "--policy-reason",
                "ok",
                "--policy-contract",
                "aiir://policy/x",
                "--json",
            ]
        )
        self.assertEqual(code, 0)
        receipt = json.loads(out)
        self.assertEqual(receipt["contract_version"], "aiir/agent_receipt.v0.1")
        self.assertTrue(receipt["record_id"].startswith("a1-"))
        self.assertEqual(receipt["policy"]["decision"], "allowed")
        self.assertTrue(verify_receipt(receipt)["valid"])

    def test_emit_to_ledger(self):
        with tempfile.TemporaryDirectory() as tmp, _in_dir(tmp):
            code, _ = _run(
                [
                    "agent",
                    "emit",
                    "--action",
                    "run",
                    "--tool",
                    "claude-code",
                    "--ledger",
                    ".aiir",
                ]
            )
            self.assertEqual(code, 0)
            receipts = _read_ledger(".aiir")
            self.assertEqual(len(receipts), 1)
            self.assertEqual(receipts[0]["contract_version"], "aiir/agent_receipt.v0.1")

    def test_emit_bad_artifact_fails(self):
        code, _ = _run(
            [
                "agent",
                "emit",
                "--action",
                "edit",
                "--tool",
                "x",
                "--input",
                "bogus",
                "--json",
            ]
        )
        self.assertEqual(code, 1)

    def test_emit_build_error_fails(self):
        # Empty tool name fails normalization (fail-closed, exit 1).
        code, _ = _run(["agent", "emit", "--action", "edit", "--tool", "", "--json"])
        self.assertEqual(code, 1)


class TestAgentVerify(unittest.TestCase):
    def _write(self, obj):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(obj, f)
        f.close()
        return f.name

    def test_verify_valid(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="t", action_kind="run"
        )
        code, _ = _run(["agent", "verify", self._write(r)])
        self.assertEqual(code, 0)

    def test_verify_tampered(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="t", action_kind="run"
        )
        r["action"]["kind"] = "deploy"
        code, _ = _run(["agent", "verify", self._write(r)])
        self.assertEqual(code, 1)

    def test_verify_not_agent_receipt(self):
        code, _ = _run(
            ["agent", "verify", self._write({"type": "aiir.commit_receipt"})]
        )
        self.assertEqual(code, 1)

    def test_verify_unreadable(self):
        code, _ = _run(["agent", "verify", "/nonexistent/path/x.json"])
        self.assertEqual(code, 1)


class TestAgentNoSubcommand(unittest.TestCase):
    def test_help_returns_2(self):
        code, _ = _run(["agent"])
        self.assertEqual(code, 2)


class TestVerifyRoutesAgent(unittest.TestCase):
    def test_flat_verify_on_agent_receipt(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="cursor", action_kind="edit"
        )
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ar.json"
            f.write_text(json.dumps(r), encoding="utf-8")
            # Flat --verify must route to the agent verifier and exit 0.
            code, _ = _run(["--verify", str(f)])
            self.assertEqual(code, 0)
            # And the file verifier returns an agent verdict.
            result = verify_receipt_file(str(f))
            self.assertTrue(result["valid"])
            self.assertEqual(result["receipt_type"], "agent_receipt")


class TestLedgerRoutesAgent(unittest.TestCase):
    def test_append_and_dedup(self):
        r = build_agent_receipt(
            actor_kind="agent", actor_tool_name="t", action_kind="run"
        )
        with tempfile.TemporaryDirectory() as tmp, _in_dir(tmp):
            append_to_ledger([r], ledger_dir=".aiir")
            append_to_ledger([r], ledger_dir=".aiir")  # same record_id → deduped
            receipts = _read_ledger(".aiir")
            self.assertEqual(len(receipts), 1)


if __name__ == "__main__":
    unittest.main()
