#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR Witness Attestor — generate in-toto Statement v1 attestations
from AIIR receipts for use in Witness attestation pipelines.

This is a standalone Python attestor that produces attestations compatible
with the Witness framework (https://github.com/in-toto/witness). It can
be used independently or as a reference for a Go-native Witness plugin.

Usage:
    # Attest the current commit
    python attestor.py --commit HEAD --output attestation.intoto.json

    # Attest a range of commits
    python attestor.py --range origin/main..HEAD --output-dir attestations/

    # Verify and attest
    python attestor.py --verify .aiir/receipts.jsonl --output verification.intoto.json

Zero external dependencies — uses only Python standard library + aiir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional


INTOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
AIIR_PREDICATE_TYPES = {
    "aiir/commit_receipt.v1": "https://invariantsystems.io/predicates/aiir/commit_receipt/v1",
    "aiir/commit_receipt.v2": "https://invariantsystems.io/predicates/aiir/commit_receipt/v2",
}
AIIR_VERIFICATION_PREDICATE_TYPE = (
    "https://invariantsystems.io/predicates/aiir/verification_result/v1"
)


def _predicate_type_for_receipt(receipt: Dict[str, Any]) -> str:
    """Return the predicate URI matching the wrapped AIIR receipt schema."""
    schema = str(receipt.get("schema") or "aiir/commit_receipt.v2")
    return AIIR_PREDICATE_TYPES.get(
        schema,
        AIIR_PREDICATE_TYPES["aiir/commit_receipt.v2"],
    )


def run_aiir(args: List[str]) -> str:
    """Run the aiir CLI and return stdout."""
    cmd = [sys.executable, "-m", "aiir"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"aiir error: {result.stderr}", file=sys.stderr)
        raise SystemExit(1)
    return result.stdout


def generate_receipt(
    commit: str = "HEAD",
    commit_range: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generate AIIR receipts for one or more commits."""
    args = ["--json"]
    if commit_range:
        args.extend(["--range", commit_range])
    else:
        args.extend(["--commit", commit])

    output = run_aiir(args)
    receipts = []
    for line in output.strip().splitlines():
        if line.strip():
            try:
                receipts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return receipts


def receipt_to_statement(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap an AIIR receipt in an in-toto Statement v1 envelope."""
    commit_obj = receipt.get("commit", {})
    if not isinstance(commit_obj, dict):
        commit_obj = {}

    sha = commit_obj.get("sha", "")
    prov = receipt.get("provenance", {})
    if not isinstance(prov, dict):
        prov = {}
    repo = prov.get("repository") or "unknown"

    subject_name = f"{repo}@{sha}" if sha else repo

    return {
        "_type": INTOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": subject_name,
                "digest": {"gitCommit": str(sha)},
            }
        ],
        "predicateType": _predicate_type_for_receipt(receipt),
        "predicate": receipt,
    }


def verify_to_statement(
    ledger_path: str,
) -> Dict[str, Any]:
    """Verify AIIR receipts and produce a verification-result attestation."""
    output = run_aiir(["--verify", ledger_path, "--json"])
    results = []
    for line in output.strip().splitlines():
        if line.strip():
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    valid = sum(1 for r in results if r.get("valid", False))
    invalid = len(results) - valid

    return {
        "_type": INTOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": ledger_path,
                "digest": {"sha256": ""},  # could hash the ledger file
            }
        ],
        "predicateType": AIIR_VERIFICATION_PREDICATE_TYPE,
        "predicate": {
            "verifier": "aiir",
            "receipts_checked": len(results),
            "valid": valid,
            "invalid": invalid,
            "results": results,
        },
    }


def write_statement(statement: Dict[str, Any], path: str) -> None:
    """Write an in-toto statement to a file."""
    with open(path, "w") as f:
        json.dump(statement, f, indent=2)
        f.write("\n")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="AIIR Witness Attestor — generate in-toto attestations"
    )
    parser.add_argument(
        "--commit",
        default="HEAD",
        help="Commit to attest (default: HEAD)",
    )
    parser.add_argument(
        "--range",
        dest="commit_range",
        help="Commit range to attest (e.g., origin/main..HEAD)",
    )
    parser.add_argument(
        "--verify",
        dest="verify_ledger",
        help="Verify a ledger file and produce verification attestation",
    )
    parser.add_argument(
        "--output",
        help="Output file for a single attestation",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for multiple attestations",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write JSONL to stdout",
    )
    args = parser.parse_args()

    if args.verify_ledger:
        statement = verify_to_statement(args.verify_ledger)
        if args.output:
            write_statement(statement, args.output)
            print(f"Wrote verification attestation to {args.output}",
                  file=sys.stderr)
        else:
            print(json.dumps(statement, indent=2))
        return 0

    receipts = generate_receipt(
        commit=args.commit,
        commit_range=args.commit_range,
    )
    statements = [receipt_to_statement(r) for r in receipts]

    if args.output and len(statements) == 1:
        write_statement(statements[0], args.output)
        print(f"Wrote attestation to {args.output}", file=sys.stderr)
    elif args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        for stmt in statements:
            sha = (
                stmt.get("subject", [{}])[0]
                .get("digest", {})
                .get("gitCommit", "unknown")
            )
            path = os.path.join(
                args.output_dir, f"aiir-{sha[:12]}.intoto.json"
            )
            write_statement(stmt, path)
        print(
            f"Wrote {len(statements)} attestations to {args.output_dir}/",
            file=sys.stderr,
        )
    elif args.stdout:
        for stmt in statements:
            print(json.dumps(stmt, separators=(",", ":")))
    else:
        for stmt in statements:
            print(json.dumps(stmt, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
