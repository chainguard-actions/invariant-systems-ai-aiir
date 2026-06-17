#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
IBM Quantum workload provenance via Qiskit.

Requires: pip install qiskit qiskit-ibm-runtime aiir
"""

from aiir.quantum import (
    PROVIDER_IBM,
    bind,
    package,
    save_bundle,
    verify,
)

# ── 1. Package the workload ────────────────────────────────────────
qasm = """\
OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q[0];
cx q[0], q[1];
cx q[0], q[2];
c = measure q;
"""

pkg = package(qasm, shots=1024, provider=PROVIDER_IBM)
print(f"Packaged: {pkg['content_hash'][:24]}…")

# ── 2. Execute on IBM hardware ─────────────────────────────────────
# Uncomment and fill in your credentials to run on real hardware:
#
# from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
# from qiskit import QuantumCircuit
#
# service = QiskitRuntimeService(channel="ibm_quantum_platform")
# backend = service.least_busy(operational=True, min_num_qubits=3)
#
# qc = QuantumCircuit(3, 3)
# qc.h(0)
# qc.cx(0, 1)
# qc.cx(0, 2)
# qc.measure([0, 1, 2], [0, 1, 2])
#
# sampler = SamplerV2(mode=backend)
# job = sampler.run([qc], shots=1024)
# result = job.result()
# job_id = job.job_id()
# backend_name = backend.name

# For this example, use a placeholder:
job_id = "d7chbab0g7hs73dqrvh0"
backend_name = "ibm_kingston"

# ── 3. Bind ────────────────────────────────────────────────────────
bundle = bind(
    pkg,
    job_id=job_id,
    backend=backend_name,
    metadata={"qiskit_version": "2.3.1"},
)
print(f"Bound:    {bundle['binding']['binding_hash'][:24]}…")

# ── 4. Verify and save ────────────────────────────────────────────
assert verify(bundle)
save_bundle(bundle, "ibm_bundle.json")
print("Verified: ✅  →  ibm_bundle.json")
