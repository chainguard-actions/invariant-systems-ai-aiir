#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Generic quantum workload provenance — no SDK required.

Shows the full package → bind → verify → save workflow using only AIIR
(zero dependencies). Replace ``job_id`` and ``backend`` with your real
execution handle from any provider.
"""

from aiir.quantum import (
    PROVIDER_GENERIC,
    bind,
    load_bundle,
    package,
    save_bundle,
    verify,
    verify_or_explain,
)

# ── 1. Package ──────────────────────────────────────────────────────
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

pkg = package(
    qasm,
    shots=2048,
    provider=PROVIDER_GENERIC,
    backend="my-local-simulator",
    name="ghz3-demo",
    metadata={"description": "3-qubit GHZ state for provenance demo"},
)
print(f"Packaged: {pkg['content_hash'][:24]}…")

# ── 2. Bind (after execution) ──────────────────────────────────────
bundle = bind(
    pkg,
    job_id="demo-job-001",
    backend="my-local-simulator",
    metadata={"simulator_version": "1.0.0"},
)
print(f"Bound:    {bundle['binding']['binding_hash'][:24]}…")

# ── 3. Verify ──────────────────────────────────────────────────────
ok, reasons = verify_or_explain(bundle)
assert ok, f"Verification failed: {reasons}"
print("Verified: ✅")

# ── 4. Save ────────────────────────────────────────────────────────
save_bundle(bundle, "bundle.json")
print("Saved:    bundle.json")

# ── 5. Load and re-verify ─────────────────────────────────────────
loaded = load_bundle("bundle.json")
assert verify(loaded)
print("Reload:   ✅ bundle.json re-verified")

# ── 6. Tamper detection ───────────────────────────────────────────
loaded["execution"]["job_id"] = "TAMPERED"
ok2, reasons2 = verify_or_explain(loaded)
assert not ok2
print(f"Tamper:   ❌ caught ({reasons2[0]})")

print("\nDone — full provenance lifecycle in 6 steps.")
