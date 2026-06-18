#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AWS Braket workload provenance.

Requires: pip install amazon-braket-sdk aiir
"""

from aiir.quantum import (
    PROVIDER_BRAKET,
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

pkg = package(qasm, shots=1024, provider=PROVIDER_BRAKET)
print(f"Packaged: {pkg['content_hash'][:24]}…")

# ── 2. Execute on Braket ───────────────────────────────────────────
# Uncomment to run on a real Braket backend:
#
# from braket.aws import AwsDevice
# from braket.circuits import Circuit
#
# device = AwsDevice("arn:aws:braket:us-east-1::device/qpu/ionq/Aria-1")
# circuit = Circuit().h(0).cnot(0, 1).cnot(0, 2)
# task = device.run(circuit, shots=1024)
# result = task.result()
# job_id = task.id
# backend_name = device.name

# Placeholder for this example:
job_id = "arn:aws:braket:us-east-1:123456789:quantum-task/abc-123"
backend_name = "Aria-1"

# ── 3. Bind ────────────────────────────────────────────────────────
bundle = bind(
    pkg,
    job_id=job_id,
    backend=backend_name,
    metadata={"braket_sdk_version": "1.88.0"},
)
print(f"Bound:    {bundle['binding']['binding_hash'][:24]}…")

# ── 4. Verify and save ────────────────────────────────────────────
assert verify(bundle)
save_bundle(bundle, "braket_bundle.json")
print("Verified: ✅  →  braket_bundle.json")
