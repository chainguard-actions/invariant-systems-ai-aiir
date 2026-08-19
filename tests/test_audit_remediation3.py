# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Regression tests for the security-pass-2 medium/low remediations.

- _verify_cbor: reject maps whose keys collapse as Python objects (0 vs 0.0).
- _ledger: O_NOFOLLOW refuses a symlinked receipts.jsonl (no arbitrary clobber).
- cli `aiir agent verify`: refuse symlinks and oversized files.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from aiir import cli
from aiir._ledger import append_to_ledger
from aiir._verify_cbor import CborDecodeError, decode_cbor_full


@contextlib.contextmanager
def _in_dir(path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _run(argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue() + err.getvalue()


class TestCborDuplicateKeyCollapse(unittest.TestCase):
    def test_int_and_float_zero_keys_rejected(self):
        # map(2): key int 0 (0x00) -> val 0x00 ; key half-float 0.0 (0xf9 0x00 0x00)
        # -> val 0x01. Bytewise order passes (00 < f9..), but 0 == 0.0 in Python,
        # so the keys would collapse — must be rejected, not silently decoded.
        blob = bytes([0xA2, 0x00, 0x00, 0xF9, 0x00, 0x00, 0x01])
        with self.assertRaises(CborDecodeError):
            decode_cbor_full(blob)

    def test_distinct_keys_still_decode(self):
        # map(2): "a"->1, "b"->2 — distinct keys, must still round-trip.
        blob = bytes([0xA2, 0x61, 0x61, 0x01, 0x61, 0x62, 0x02])
        self.assertEqual(decode_cbor_full(blob), {"a": 1, "b": 2})


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW is POSIX-only")
class TestLedgerSymlinkRefusal(unittest.TestCase):
    def test_symlinked_ledger_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp, _in_dir(tmp):
            victim = Path(tmp) / "victim.txt"
            victim.write_text("untouched", encoding="utf-8")
            aiir_dir = Path(tmp) / ".aiir"
            aiir_dir.mkdir()
            # Attacker pre-places a symlink where the ledger file would be.
            os.symlink(victim, aiir_dir / "receipts.jsonl")
            receipt = {
                "type": "aiir.commit_receipt",
                "commit": {"sha": "a" * 40},
            }
            with self.assertRaises(OSError):
                append_to_ledger([receipt], ledger_dir=".aiir")
            # The victim file was not clobbered through the symlink.
            self.assertEqual(victim.read_text(encoding="utf-8"), "untouched")


class TestAgentVerifyReadGuards(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unsupported")
    def test_verify_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_text("{}", encoding="utf-8")
            link = Path(tmp) / "link.json"
            try:
                os.symlink(real, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink not permitted in this environment")
            code, out = _run(["agent", "verify", str(link)])
            self.assertEqual(code, 1)
            self.assertIn("symlink", out.lower())

    def test_verify_refuses_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = Path(tmp) / "big.json"
            big.write_text("{}", encoding="utf-8")
            # Patch the cap low so we don't have to write a multi-MB fixture.
            original = cli.MAX_RECEIPT_FILE_SIZE
            cli.MAX_RECEIPT_FILE_SIZE = 1
            try:
                code, out = _run(["agent", "verify", str(big)])
            finally:
                cli.MAX_RECEIPT_FILE_SIZE = original
            self.assertEqual(code, 1)
            self.assertIn("too large", out.lower())


if __name__ == "__main__":
    unittest.main()
