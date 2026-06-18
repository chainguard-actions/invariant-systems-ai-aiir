#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Google Cirq workload provenance.

Requires: pip install cirq aiir
"""

from aiir.quantum import (
    PROVIDER_CIRQ,
    bind,
    package,
    save_bundle,
    verify,
)

# ── 1. Package ─────────────────────────────────────────────────────
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

pkg = package(qasm, shots=1024, provider=PROVIDER_CIRQ)
print(f"Packaged: {pkg['content_hash'][:24]}…")

# ── 2. Execute on Cirq ─────────────────────────────────────────────
# Uncomment to run on a real Cirq simulator or Google hardware:
#
# import cirq
#
# q = cirq.LineQubit.range(3)
# circuit = cirq.Circuit([
#     cirq.H(q[0]),
#     cirq.CNOT(q[0], q[1]),
#     cirq.CNOT(q[0], q[2]),
#     cirq.measure(*q, key="result"),
# ])
#
# sim = cirq.Simulator()
# result = sim.run(circuit, repetitions=1024)
# job_id = "cirq-sim-" + cirq.value.big_endian_int_to_digits(
#     hash(str(result)), digit_count=8, base=16
# )

# Placeholder for this example:
job_id = "cirq-sim-abc12345"
backend_name = "cirq-simulator"

# ── 3. Bind ────────────────────────────────────────────────────────
bundle = bind(
    pkg,
    job_id=job_id,
    backend=backend_name,
    metadata={"cirq_version": "1.4.0"},
)
print(f"Bound:    {bundle['binding']['binding_hash'][:24]}…")

# ── 4. Verify and save ────────────────────────────────────────────
assert verify(bundle)
save_bundle(bundle, "cirq_bundle.json")
print("Verified: ✅  →  cirq_bundle.json")
