#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Convert AIIR receipt ledger entries into in-toto Statement v1 attestations
suitable for GUAC ingestion.

Usage:
    # Convert a ledger file (one in-toto statement per receipt)
    python aiir_to_guac.py .aiir/receipts.jsonl --output-dir attestations/

    # Convert and ingest into GUAC in one step
    python aiir_to_guac.py .aiir/receipts.jsonl --stdout | guacone collect files /dev/stdin

    # Filter to AI-classified receipts only
    python aiir_to_guac.py .aiir/receipts.jsonl --ai-only --output-dir attestations/

Zero external dependencies — uses only Python standard library.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List


INTOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
AIIR_PREDICATE_TYPES = {
    "aiir/commit_receipt.v1": "https://invariantsystems.io/predicates/aiir/commit_receipt/v1",
    "aiir/commit_receipt.v2": "https://invariantsystems.io/predicates/aiir/commit_receipt/v2",
}


def _predicate_type_for_receipt(receipt: Dict[str, Any]) -> str:
    """Return the predicate URI matching the wrapped AIIR receipt schema."""
    schema = str(receipt.get("schema") or "aiir/commit_receipt.v2")
    return AIIR_PREDICATE_TYPES.get(
        schema,
        AIIR_PREDICATE_TYPES["aiir/commit_receipt.v2"],
    )


def receipt_to_intoto(receipt: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap an AIIR receipt in an in-toto Statement v1 envelope."""
    commit = receipt.get("commit", {})
    if not isinstance(commit, dict):
        commit = {}

    sha = commit.get("sha", "")
    prov = receipt.get("provenance", {})
    if not isinstance(prov, dict):
        prov = {}
    repo_url = prov.get("repository") or "unknown"

    subject_name = f"{repo_url}@{sha}" if sha else repo_url

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


def load_ledger(path: str) -> List[Dict[str, Any]]:
    """Load receipts from an AIIR JSONL ledger file."""
    receipts: List[Dict[str, Any]] = []
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                # Skip index/meta records
                if obj.get("type") in ("aiir/commit_receipt", None):
                    receipts.append(obj)
                elif "commit" in obj and "content_hash" in obj:
                    receipts.append(obj)
            except json.JSONDecodeError:
                print(
                    f"warning: skipping malformed line {line_no}",
                    file=sys.stderr,
                )
    return receipts


def is_ai_classified(receipt: Dict[str, Any]) -> bool:
    """Check if a receipt is classified as AI-involved."""
    att = receipt.get("ai_attestation", {})
    if not isinstance(att, dict):
        return False
    # v2 field is authorship_class; v1 used classification
    ac = att.get("authorship_class") or att.get("classification", "")
    return ac in ("ai_assisted", "ai_generated", "bot")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert AIIR receipts to in-toto statements for GUAC"
    )
    parser.add_argument("ledger", help="Path to AIIR JSONL ledger file")
    parser.add_argument(
        "--output-dir",
        help="Write individual .intoto.json files to this directory",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write JSONL to stdout (one statement per line)",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Only include AI-classified receipts",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary statistics",
    )
    args = parser.parse_args()

    receipts = load_ledger(args.ledger)
    if args.ai_only:
        receipts = [r for r in receipts if is_ai_classified(r)]

    statements = [receipt_to_intoto(r) for r in receipts]

    if args.summary or (not args.stdout and not args.output_dir):
        total = len(statements)
        ai_count = sum(1 for r in receipts if is_ai_classified(r))
        human_count = total - ai_count
        print(f"Receipts:       {total}")
        print(f"  AI-classified: {ai_count}")
        print(f"  Human:         {human_count}")
        print(f"Predicate type: {AIIR_PREDICATE_TYPE}")

        if not args.stdout and not args.output_dir:
            print(
                "\nUse --stdout or --output-dir to emit in-toto statements."
            )
            return 0

    if args.stdout:
        for stmt in statements:
            print(json.dumps(stmt, separators=(",", ":")))

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        for i, stmt in enumerate(statements):
            sha = (
                stmt.get("subject", [{}])[0]
                .get("digest", {})
                .get("gitCommit", f"unknown-{i}")
            )
            filename = f"aiir-{sha[:12]}.intoto.json"
            path = os.path.join(args.output_dir, filename)
            with open(path, "w") as f:
                json.dump(stmt, f, indent=2)
                f.write("\n")
        print(
            f"Wrote {len(statements)} in-toto statements to {args.output_dir}/",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
