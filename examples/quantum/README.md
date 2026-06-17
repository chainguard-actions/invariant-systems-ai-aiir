# Quantum Workload Provenance

Record exactly what ran, where, when, and prove it wasn't tampered with —
in 60 seconds, with any quantum SDK.

## Quick start (no quantum SDK needed)

```python
from aiir.quantum import package, bind, verify

# 1. Package a workload
qasm = """
OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q[0];
cx q[0], q[1];
cx q[0], q[2];
c = measure q;
"""
pkg = package(qasm, shots=1024, provider="ibm-quantum", backend="ibm_fez")

# 2. After running on hardware, bind the execution handle
bundle = bind(pkg, job_id="d7chbab0g7hs73dqrvh0", backend="ibm_fez")

# 3. Verify internal consistency
assert verify(bundle), "Bundle should verify cleanly"

# 4. Tamper detection works
bundle["execution"]["job_id"] = "TAMPERED"
assert not verify(bundle), "Tampered bundle should fail"
```

## Vendor examples

The module works with any provider — see the scripts in this directory:

| Script            | Provider    | SDK needed?                          |
| ----------------- | ----------- | ------------------------------------ |
| `ibm_qiskit.py`   | IBM Quantum | Yes (`qiskit`, `qiskit-ibm-runtime`) |
| `google_cirq.py`  | Google Cirq | Yes (`cirq`)                         |
| `aws_braket.py`   | AWS Braket  | Yes (`amazon-braket-sdk`)            |
| `any_provider.py` | Generic     | No — stdlib only                     |

All scripts produce a `bundle.json` that can be verified with:

```bash
python -c "
from aiir.quantum import load_bundle, verify
b = load_bundle('bundle.json')
print('✅ Verified' if verify(b) else '❌ Tampered')
"
```

## What's in a bundle?

A provenance bundle contains three layers:

```text
{
  "schema": "aiir.quantum.provenance_bundle.v1",
  "workload": {              ← what you intended to run
    "schema": "aiir.quantum.workload_package.v1",
    "name": "workload",
    "provider": "ibm-quantum",
    "runtime": {
      "shots": 1024,
      "backend": "ibm_fez",
      "optimization_level": 1
    },
    "artifacts": {
      "qasm": "..."
    },
    "logical_workload_hash": "sha256:...",
    "content_hash": "sha256:...",
    "created_at": "2026-05-01T00:00:00Z"
  },
  "execution": {             ← what actually ran
    "schema": "aiir.quantum.execution_record.v1",
    "job_id": "abc123",
    "backend": "ibm_fez",
    "provider": "ibm-quantum",
    "submitted_at": "2026-05-01T00:01:00Z"
  },
  "binding": {
    "workload_hash": "sha256:...",
    "package_hash": "sha256:...",
    "execution_hash": "sha256:...",
    "binding_hash": "sha256:...",
    "bound_at": "2026-05-01T00:01:01Z"
  },
  "created_at": "2026-05-01T00:01:01Z"
}
```

`workload.logical_workload_hash` and `binding.workload_hash` track the stable
logical workload identity from the exact OpenQASM bytes only. The package's
`content_hash` and the binding's `package_hash` still protect the full packaged
workload, including runtime hints and timestamps. `verify()` recomputes the
logical workload hash, package hash, execution hash, and binding hash and
confirms they match. If anyone changes a single byte — even a whitespace change
in the QASM — verification fails.

## Schema identifiers

- `aiir.quantum.logical_workload_identity.v1`: stable logical workload identity from exact QASM bytes.
- `aiir.quantum.workload_package.v1`: workload intent, including QASM and runtime parameters.
- `aiir.quantum.execution_record.v1`: execution handle, including provider job ID and backend.
- `aiir.quantum.provenance_bundle.v1`: complete bundle tying workload, execution, and binding together.

## FAQ

**Q: Do I need AIIR installed to verify a bundle?**
A: Yes — `pip install aiir`. But AIIR has zero dependencies (stdlib-only), so
it installs in under a second.

**Q: Does this work with simulators?**
A: Yes. Set `provider="generic"` and any backend name. The bundle records
whatever you tell it.

**Q: Can I add custom metadata?**
A: Yes. Pass `metadata={"key": "value"}` to `package()` and/or `bind()`.
Custom metadata is included in the content hash.

**Q: How does this relate to AIIR git-commit receipts?**
A: AIIR receipts prove what code was committed and whether AI assisted.
Quantum bundles prove what workload ran on what hardware. They complement
each other — use both for full provenance.
