# Quantum Workload Provenance in CI

Use AIIR's quantum module in GitHub Actions to attest quantum workloads
alongside your regular commit receipts.

## Example workflow

```yaml
name: Quantum Provenance
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  id-token: write    # Sigstore signing
  contents: read
  checks: write
  pull-requests: write

jobs:
  quantum-attest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      # ── 1. Generate git-commit receipts ──
      - uses: invariant-systems-ai/aiir@v1

      # ── 2. Run quantum workload and generate provenance ──
      - uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405  # v6.2.0
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install aiir qiskit qiskit-ibm-runtime

      - name: Run quantum workload
        env:
          IBM_QUANTUM_TOKEN: ${{ secrets.IBM_QUANTUM_TOKEN }}
        run: |
          python - <<'SCRIPT'
          from aiir.quantum import package, bind, save_bundle, verify

          # Package the workload
          qasm = open("circuits/ghz3.qasm").read()
          pkg = package(qasm, shots=1024, provider="ibm-quantum")

          # Execute on IBM hardware
          from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
          from qiskit import QuantumCircuit
          import os

          service = QiskitRuntimeService(
              channel="ibm_quantum_platform",
              token=os.environ["IBM_QUANTUM_TOKEN"],
          )
          backend = service.least_busy(operational=True, min_num_qubits=3)
          qc = QuantumCircuit(3, 3)
          qc.h(0); qc.cx(0, 1); qc.cx(0, 2); qc.measure([0,1,2], [0,1,2])

          sampler = SamplerV2(mode=backend)
          job = sampler.run([qc], shots=1024)
          result = job.result()

          # Bind and verify
          bundle = bind(pkg, job_id=job.job_id(), backend=backend.name)
          assert verify(bundle), "Bundle verification failed"
          save_bundle(bundle, "quantum-bundle.json")
          print(f"✅ Quantum provenance: {bundle['binding']['binding_hash'][:24]}…")
          SCRIPT

      # ── 3. Upload provenance bundle ──
      - uses: actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f  # v7.0.0
        with:
          name: quantum-provenance
          path: quantum-bundle.json
          retention-days: 90
```

## Verifying a bundle in CI

Add a verification step to any workflow:

```yaml
      - name: Verify quantum provenance
        run: |
          python -c "
          from aiir.quantum import load_bundle, verify, verify_or_explain
          bundle = load_bundle('quantum-bundle.json')
          ok, reasons = verify_or_explain(bundle)
          if not ok:
              for r in reasons:
                  print(f'::error::{r}')
              raise SystemExit(1)
          print('✅ Quantum provenance verified')
          "
```

## Without hardware (simulator-only CI)

For CI environments without quantum hardware credentials, use any provider:

```yaml
      - name: Package and verify (no hardware)
        run: |
          python -c "
          from aiir.quantum import package, bind, verify
          pkg = package('OPENQASM 3.0; qubit[2] q; h q[0]; cx q[0],q[1];',
                        shots=100, provider='generic', backend='ci-simulator')
          bundle = bind(pkg, job_id='ci-run-\${{ github.run_id }}', backend='ci-simulator')
          assert verify(bundle)
          print('✅ Provenance chain verified')
          "
```

## Combining with commit receipts

The AIIR GitHub Action (`invariant-systems-ai/aiir@v1`) generates commit receipts.
Quantum bundles are complementary — they prove **what ran on hardware**, while
commit receipts prove **what code was committed**.

Use both in the same workflow for full provenance:

- Commit receipt → "this exact code was committed, AI involvement declared"
- Quantum bundle → "this exact QASM ran on this exact backend with these results"
