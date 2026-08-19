# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""Tests for quantum workload provenance helpers."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import aiir._quantum as quantum_module

from aiir._quantum import (
    BUNDLE_SCHEMA,
    PROVIDER_BRAKET,
    PROVIDER_CIRQ,
    PROVIDER_GENERIC,
    PROVIDER_IBM,
    PROVIDER_IONQ,
    PROVIDER_PENNYLANE,
    PROVIDER_RIGETTI,
    WORKLOAD_SCHEMA,
    _constant_time_compare,
    _content_hash,
    _logical_workload_core,
    _now_rfc3339,
    bind,
    load_bundle,
    package,
    save_bundle,
    verify,
    verify_or_explain,
)


GHZ3_QASM = """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q[0];
cx q[0], q[1];
cx q[0], q[2];
c = measure q;
"""


class TestPackage(unittest.TestCase):
    """Tests for :func:`package`."""

    def test_logical_workload_core_requires_artifacts_dict(self):
        with self.assertRaises(TypeError):
            _logical_workload_core({})

    def test_logical_workload_core_requires_non_empty_qasm(self):
        with self.assertRaises(TypeError):
            _logical_workload_core({"artifacts": {"qasm": ""}})

    def test_basic_package(self):
        pkg = package(GHZ3_QASM, shots=2048, provider=PROVIDER_IBM, name="ghz3")
        self.assertEqual(pkg["schema"], WORKLOAD_SCHEMA)
        self.assertEqual(pkg["name"], "ghz3")
        self.assertEqual(pkg["provider"], PROVIDER_IBM)
        self.assertEqual(pkg["runtime"]["shots"], 2048)
        self.assertEqual(pkg["runtime"]["backend"], "auto")
        self.assertEqual(pkg["artifacts"]["qasm"], GHZ3_QASM)
        self.assertIn("content_hash", pkg)
        self.assertTrue(pkg["content_hash"].startswith("sha256:"))
        self.assertIn("created_at", pkg)

    def test_defaults(self):
        pkg = package(GHZ3_QASM)
        self.assertEqual(pkg["runtime"]["shots"], 1024)
        self.assertEqual(pkg["provider"], PROVIDER_GENERIC)
        self.assertEqual(pkg["name"], "workload")

    def test_description(self):
        pkg = package(GHZ3_QASM, description="test desc")
        self.assertEqual(pkg["description"], "test desc")

    def test_no_description(self):
        pkg = package(GHZ3_QASM)
        self.assertNotIn("description", pkg)

    def test_metadata(self):
        pkg = package(GHZ3_QASM, metadata={"experiment": "exp01"})
        self.assertEqual(pkg["metadata"]["experiment"], "exp01")

    def test_no_metadata(self):
        pkg = package(GHZ3_QASM)
        self.assertNotIn("metadata", pkg)

    def test_custom_backend(self):
        pkg = package(GHZ3_QASM, backend="ibm_fez")
        self.assertEqual(pkg["runtime"]["backend"], "ibm_fez")

    def test_optimization_level(self):
        pkg = package(GHZ3_QASM, optimization_level=3)
        self.assertEqual(pkg["runtime"]["optimization_level"], 3)

    def test_empty_qasm_raises(self):
        with self.assertRaises(ValueError):
            package("")

    def test_non_string_qasm_raises(self):
        with self.assertRaises(ValueError):
            package(123)  # type: ignore[arg-type]

    def test_whitespace_only_qasm_raises(self):
        with self.assertRaises(ValueError):
            package("   ")

    def test_zero_shots_raises(self):
        with self.assertRaises(ValueError):
            package(GHZ3_QASM, shots=0)

    def test_negative_shots_raises(self):
        with self.assertRaises(ValueError):
            package(GHZ3_QASM, shots=-1)

    def test_non_int_shots_raises(self):
        with self.assertRaises(ValueError):
            package(GHZ3_QASM, shots=1.5)  # type: ignore[arg-type]

    def test_logical_workload_hash_deterministic(self):
        """Same logical workload produces the same logical hash."""
        pkg1 = package(GHZ3_QASM, shots=1024, name="test")
        pkg2 = package(GHZ3_QASM, shots=1024, name="test")
        self.assertEqual(pkg1["logical_workload_hash"], pkg2["logical_workload_hash"])

    def test_logical_workload_hash_stable_across_timestamps(self):
        with patch.object(
            quantum_module,
            "_now_rfc3339",
            side_effect=["2026-05-01T00:00:00Z", "2026-05-01T00:00:01Z"],
        ):
            pkg1 = package(GHZ3_QASM, provider=PROVIDER_IBM, backend="ibm_fez")
            pkg2 = package(GHZ3_QASM, provider=PROVIDER_IBM, backend="ibm_fez")

        self.assertEqual(pkg1["logical_workload_hash"], pkg2["logical_workload_hash"])
        self.assertNotEqual(pkg1["content_hash"], pkg2["content_hash"])

    def test_logical_workload_hash_stable_across_provider_hints(self):
        pkg1 = package(GHZ3_QASM, provider=PROVIDER_IBM, backend="ibm_fez")
        pkg2 = package(GHZ3_QASM, provider=PROVIDER_BRAKET, backend="sv1")

        self.assertEqual(pkg1["logical_workload_hash"], pkg2["logical_workload_hash"])
        self.assertNotEqual(pkg1["content_hash"], pkg2["content_hash"])

    def test_file_path_qasm(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".qasm", delete=False) as fh:
            fh.write(GHZ3_QASM)
            fh.flush()
            path = fh.name

        try:
            pkg = package(path)
            self.assertEqual(pkg["artifacts"]["qasm"], GHZ3_QASM)
        finally:
            os.unlink(path)

    def test_file_path_nonexistent(self):
        """A .qasm path that doesn't exist is treated as literal text."""
        pkg = package("/nonexistent/path.qasm")
        self.assertEqual(pkg["artifacts"]["qasm"], "/nonexistent/path.qasm")

    def test_all_providers(self):
        for prov in [
            PROVIDER_IBM,
            PROVIDER_BRAKET,
            PROVIDER_CIRQ,
            PROVIDER_RIGETTI,
            PROVIDER_IONQ,
            PROVIDER_PENNYLANE,
            PROVIDER_GENERIC,
        ]:
            pkg = package(GHZ3_QASM, provider=prov)
            self.assertEqual(pkg["provider"], prov)


class TestBind(unittest.TestCase):
    """Tests for :func:`bind`."""

    def setUp(self):
        self.pkg = package(GHZ3_QASM, shots=2048, provider=PROVIDER_IBM)

    def test_basic_bind(self):
        bundle = bind(self.pkg, job_id="abc123", backend="ibm_fez")
        self.assertEqual(bundle["schema"], BUNDLE_SCHEMA)
        self.assertIn("workload", bundle)
        self.assertIn("execution", bundle)
        self.assertIn("binding", bundle)
        self.assertEqual(bundle["execution"]["job_id"], "abc123")
        self.assertEqual(bundle["execution"]["backend"], "ibm_fez")
        self.assertEqual(bundle["execution"]["provider"], PROVIDER_IBM)

    def test_provider_override(self):
        bundle = bind(self.pkg, job_id="x", backend="sv1", provider=PROVIDER_BRAKET)
        self.assertEqual(bundle["execution"]["provider"], PROVIDER_BRAKET)

    def test_session_id(self):
        bundle = bind(self.pkg, job_id="x", backend="b", session_id="sess-123")
        self.assertEqual(bundle["execution"]["session_id"], "sess-123")

    def test_task_arn(self):
        bundle = bind(
            self.pkg,
            job_id="x",
            backend="sv1",
            task_arn="arn:aws:braket:us-east-1:123:quantum-task/abc",
        )
        self.assertEqual(
            bundle["execution"]["task_arn"],
            "arn:aws:braket:us-east-1:123:quantum-task/abc",
        )

    def test_result_counts(self):
        counts = {"000": 1009, "111": 981, "001": 9}
        bundle = bind(self.pkg, job_id="x", backend="b", result_counts=counts)
        self.assertEqual(bundle["execution"]["result_counts"], counts)

    def test_metadata(self):
        bundle = bind(self.pkg, job_id="x", backend="b", metadata={"note": "test"})
        self.assertEqual(bundle["execution"]["metadata"]["note"], "test")

    def test_submitted_at(self):
        bundle = bind(
            self.pkg, job_id="x", backend="b", submitted_at="2026-04-10T00:00:00Z"
        )
        self.assertEqual(bundle["execution"]["submitted_at"], "2026-04-10T00:00:00Z")

    def test_empty_job_id_raises(self):
        with self.assertRaises(ValueError):
            bind(self.pkg, job_id="", backend="b")

    def test_non_string_job_id_raises(self):
        with self.assertRaises(ValueError):
            bind(self.pkg, job_id=123, backend="b")  # type: ignore[arg-type]

    def test_empty_backend_raises(self):
        with self.assertRaises(ValueError):
            bind(self.pkg, job_id="x", backend="")

    def test_non_dict_package_raises(self):
        with self.assertRaises(ValueError):
            bind("not a dict", job_id="x", backend="b")  # type: ignore[arg-type]

    def test_binding_hashes_present(self):
        bundle = bind(self.pkg, job_id="x", backend="b")
        self.assertIn("workload_hash", bundle["binding"])
        self.assertIn("package_hash", bundle["binding"])
        self.assertIn("execution_hash", bundle["binding"])
        self.assertIn("binding_hash", bundle["binding"])
        self.assertTrue(bundle["binding"]["binding_hash"].startswith("sha256:"))

    def test_binding_tracks_logical_and_package_hashes(self):
        bundle = bind(self.pkg, job_id="x", backend="b")
        self.assertEqual(
            bundle["binding"]["workload_hash"],
            bundle["workload"]["logical_workload_hash"],
        )
        self.assertEqual(
            bundle["binding"]["package_hash"],
            bundle["workload"]["content_hash"],
        )

    def test_bind_backfills_missing_hashes(self):
        raw_pkg = self.pkg.copy()
        del raw_pkg["logical_workload_hash"]
        del raw_pkg["content_hash"]

        bundle = bind(raw_pkg, job_id="x", backend="b")

        self.assertEqual(
            bundle["binding"]["workload_hash"],
            bundle["workload"]["logical_workload_hash"],
        )
        self.assertEqual(
            bundle["binding"]["package_hash"],
            bundle["workload"]["content_hash"],
        )


class TestVerify(unittest.TestCase):
    """Tests for :func:`verify`."""

    def setUp(self):
        self.pkg = package(GHZ3_QASM, shots=2048, provider=PROVIDER_IBM)
        self.bundle = bind(
            self.pkg,
            job_id="d7chbab0g7hs73dqrvh0",
            backend="ibm_kingston",
            result_counts={"000": 1009, "111": 981},
        )

    def test_valid_bundle_passes(self):
        self.assertTrue(verify(self.bundle))

    def test_tamper_job_id_fails(self):
        self.bundle["execution"]["job_id"] = "TAMPERED"
        self.assertFalse(verify(self.bundle))

    def test_tamper_backend_fails(self):
        self.bundle["execution"]["backend"] = "TAMPERED"
        self.assertFalse(verify(self.bundle))

    def test_tamper_qasm_fails(self):
        self.bundle["workload"]["artifacts"]["qasm"] = "TAMPERED"
        self.assertFalse(verify(self.bundle))

    def test_tamper_counts_fails(self):
        self.bundle["execution"]["result_counts"]["000"] = 9999
        self.assertFalse(verify(self.bundle))

    def test_tamper_binding_hash_fails(self):
        self.bundle["binding"]["binding_hash"] = "sha256:" + "a" * 64
        self.assertFalse(verify(self.bundle))

    def test_tamper_workload_hash_fails(self):
        self.bundle["binding"]["workload_hash"] = "sha256:" + "b" * 64
        self.assertFalse(verify(self.bundle))

    def test_tamper_execution_hash_fails(self):
        self.bundle["binding"]["execution_hash"] = "sha256:" + "c" * 64
        self.assertFalse(verify(self.bundle))

    def test_non_dict_returns_false(self):
        self.assertFalse(verify("not a dict"))  # type: ignore[arg-type]
        self.assertFalse(verify(None))  # type: ignore[arg-type]
        self.assertFalse(verify([]))  # type: ignore[arg-type]

    def test_missing_keys_returns_false(self):
        self.assertFalse(verify({}))
        self.assertFalse(verify({"workload": {}}))
        self.assertFalse(verify({"workload": {}, "execution": {}}))

    def test_malformed_nested_sections_return_false(self):
        malformed = {
            "workload": [],
            "execution": {},
            "binding": {},
        }
        self.assertFalse(verify(malformed))

    def test_execution_and_binding_sections_must_be_dicts(self):
        self.assertFalse(verify({"workload": {}, "execution": [], "binding": {}}))
        self.assertFalse(verify({"workload": {}, "execution": {}, "binding": []}))

    def test_non_string_hash_fields_return_false(self):
        self.bundle["binding"]["workload_hash"] = 123
        self.assertFalse(verify(self.bundle))

    def test_stored_logical_workload_hash_mismatch_fails(self):
        self.bundle["workload"]["logical_workload_hash"] = "sha256:" + "d" * 64
        self.assertFalse(verify(self.bundle))

    def test_package_hash_mismatch_fails(self):
        self.bundle["binding"]["package_hash"] = "sha256:" + "e" * 64
        self.assertFalse(verify(self.bundle))

    def test_stored_content_hash_mismatch_fails(self):
        self.bundle["workload"]["content_hash"] = "sha256:" + "f" * 64
        self.assertFalse(verify(self.bundle))

    def test_roundtrip_via_json(self):
        """Bundle survives JSON serialization/deserialization."""
        text = json.dumps(self.bundle)
        restored = json.loads(text)
        self.assertTrue(verify(restored))


class TestVerifyOrExplain(unittest.TestCase):
    """Tests for :func:`verify_or_explain`."""

    def test_valid_bundle(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        ok, reasons = verify_or_explain(bundle)
        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_tampered_bundle(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        bundle["execution"]["job_id"] = "TAMPERED"
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(len(reasons) > 0)
        self.assertIn("execution", reasons[0].lower())

    def test_non_dict(self):
        ok, reasons = verify_or_explain("bad")  # type: ignore[arg-type]
        self.assertFalse(ok)
        self.assertIn("not a dict", reasons[0])

    def test_missing_key(self):
        ok, reasons = verify_or_explain({"workload": {}})
        self.assertFalse(ok)
        self.assertIn("missing", reasons[0])

    def test_malformed_nested_section(self):
        ok, reasons = verify_or_explain(
            {"workload": [], "execution": {}, "binding": {}}
        )
        self.assertFalse(ok)
        self.assertIn("workload is not a dict", reasons[0])

    def test_workload_hash_mismatch(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        bundle["workload"]["artifacts"]["qasm"] = "TAMPERED"
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("workload" in r for r in reasons))

    def test_binding_hash_mismatch(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        bundle["binding"]["binding_hash"] = "sha256:" + "f" * 64
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("binding" in r for r in reasons))

    def test_workload_hash_error(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        del bundle["binding"]["workload_hash"]
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("error" in r for r in reasons))

    def test_execution_hash_error(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        del bundle["binding"]["execution_hash"]
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("error" in r for r in reasons))

    def test_binding_hash_key_error(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        del bundle["binding"]["binding_hash"]
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("error" in r for r in reasons))

    def test_non_string_hash_reason(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        bundle["binding"]["binding_hash"] = 123
        ok, reasons = verify_or_explain(bundle)
        self.assertFalse(ok)
        self.assertTrue(any("binding" in r for r in reasons))

    def test_package_hash_error(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        bundle["workload"]["metadata"] = object()

        ok, reasons = verify_or_explain(bundle)

        self.assertFalse(ok)
        self.assertTrue(any("package hash check error" in r for r in reasons))


class TestMultiVendor(unittest.TestCase):
    """Verify the workflow works with every supported provider."""

    def _roundtrip(self, provider, job_id, backend, **kwargs):
        pkg = package(GHZ3_QASM, provider=provider, shots=1024)
        bundle = bind(pkg, job_id=job_id, backend=backend, **kwargs)
        self.assertTrue(verify(bundle))
        # Tamper and confirm failure
        bundle["execution"]["job_id"] = "TAMPERED"
        self.assertFalse(verify(bundle))

    def test_ibm(self):
        self._roundtrip(PROVIDER_IBM, "d7chbab0g7hs73dqrvh0", "ibm_kingston")

    def test_braket(self):
        self._roundtrip(
            PROVIDER_BRAKET,
            "arn:aws:braket:us-east-1:123456:quantum-task/abc-def",
            "arn:aws:braket:us-east-1::device/qpu/ionq/Aria-1",
            task_arn="arn:aws:braket:us-east-1:123456:quantum-task/abc-def",
        )

    def test_cirq(self):
        self._roundtrip(
            PROVIDER_CIRQ,
            "projects/my-proj/programs/ghz3/jobs/job-001",
            "rainbow",
        )

    def test_rigetti(self):
        self._roundtrip(PROVIDER_RIGETTI, "qcs-job-12345", "Ankaa-3")

    def test_ionq(self):
        self._roundtrip(PROVIDER_IONQ, "ionq-task-99", "ionq.aria-1")

    def test_pennylane(self):
        self._roundtrip(PROVIDER_PENNYLANE, "pl-job-abc", "lightning.qubit")

    def test_generic(self):
        self._roundtrip(PROVIDER_GENERIC, "my-custom-id", "my-simulator")

    def test_custom_provider(self):
        self._roundtrip("my-startup-quantum", "job-42", "custom-backend")


class TestIO(unittest.TestCase):
    """Tests for :func:`save_bundle` and :func:`load_bundle`."""

    def test_save_load_roundtrip(self):
        pkg = package(GHZ3_QASM)
        bundle = bind(pkg, job_id="x", backend="b")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            path = fh.name
        try:
            save_bundle(bundle, path)
            loaded = load_bundle(path)
            self.assertTrue(verify(loaded))
            self.assertEqual(loaded["execution"]["job_id"], "x")
        finally:
            os.unlink(path)

    def test_save_creates_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "bundle.json")
            pkg = package(GHZ3_QASM)
            bundle = bind(pkg, job_id="x", backend="b")
            save_bundle(bundle, path)
            loaded = load_bundle(path)
            self.assertTrue(verify(loaded))

    def test_load_non_dict_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("[1, 2, 3]")
            path = fh.name
        try:
            with self.assertRaises(ValueError):
                load_bundle(path)
        finally:
            os.unlink(path)


class TestHelpers(unittest.TestCase):
    """Tests for internal helper functions."""

    def test_now_rfc3339_format(self):
        ts = _now_rfc3339()
        self.assertTrue(ts.endswith("Z"))
        self.assertNotIn("+", ts)

    def test_content_hash_deterministic(self):
        obj = {"a": 1, "b": "two"}
        h1 = _content_hash(obj)
        h2 = _content_hash(obj)
        self.assertEqual(h1, h2)
        self.assertTrue(h1.startswith("sha256:"))

    def test_content_hash_key_order_independent(self):
        h1 = _content_hash({"a": 1, "b": 2})
        h2 = _content_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)

    def test_constant_time_compare_equal(self):
        self.assertTrue(_constant_time_compare("abc", "abc"))

    def test_constant_time_compare_unequal(self):
        self.assertFalse(_constant_time_compare("abc", "def"))

    def test_constant_time_compare_empty(self):
        self.assertTrue(_constant_time_compare("", ""))

    def test_constant_time_compare_non_strings(self):
        self.assertFalse(_constant_time_compare(1, "1"))
        self.assertFalse(_constant_time_compare("1", None))

    def test_constant_time_compare_unicode_error(self):
        self.assertFalse(_constant_time_compare("\ud800", "\ud800"))


class TestPublicImport(unittest.TestCase):
    """Test that the public import path works."""

    def test_import_quantum_module(self):
        import aiir.quantum as quantum

        self.assertTrue(callable(quantum.package))
        self.assertTrue(callable(quantum.bind))
        self.assertTrue(callable(quantum.verify))

    def test_import_providers(self):
        import aiir.quantum as quantum

        self.assertEqual(quantum.PROVIDER_IBM, "ibm-quantum")
        self.assertEqual(quantum.PROVIDER_BRAKET, "aws-braket")
        self.assertEqual(quantum.PROVIDER_CIRQ, "google-cirq")
        self.assertEqual(quantum.PROVIDER_RIGETTI, "rigetti-qcs")
        self.assertEqual(quantum.PROVIDER_IONQ, "ionq")
        self.assertEqual(quantum.PROVIDER_PENNYLANE, "pennylane")

    def test_import_schemas(self):
        import aiir.quantum as quantum

        self.assertIn("quantum", quantum.WORKLOAD_SCHEMA)
        self.assertIn("quantum", quantum.EXECUTION_SCHEMA)
        self.assertIn("quantum", quantum.BUNDLE_SCHEMA)
        self.assertTrue(hasattr(quantum, "LOGICAL_WORKLOAD_SCHEMA"))
        self.assertIn(
            "logical_workload_identity",
            getattr(quantum, "LOGICAL_WORKLOAD_SCHEMA"),
        )


if __name__ == "__main__":
    unittest.main()
