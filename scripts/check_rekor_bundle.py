#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _ensure_repo_root_on_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


def _load_aiir_modules() -> tuple[Any, Any]:
    _ensure_repo_root_on_sys_path()
    sign_mod = importlib.import_module("aiir._sign")
    transparency_mod = importlib.import_module("aiir._transparency")
    return sign_mod, transparency_mod


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_bundle(artifact_path: Path, bundle_path: Path) -> list[str]:
    sign_mod, _ = _load_aiir_modules()
    bundle = _load_json(bundle_path)
    return sign_mod.validate_sigstore_bundle(artifact_path.read_bytes(), bundle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sanity-check a Rekor bundle against an artifact, and optionally "
            "verify the signed checkpoint and witness cosignatures offline."
        ),
    )
    parser.add_argument("--artifact", required=True, help="Path to the signed artifact")
    parser.add_argument(
        "--bundle",
        "--rekor-bundle",
        dest="bundle",
        required=True,
        help="Path to the .sigstore bundle or aiir.rekor.bundle.v1 document",
    )
    parser.add_argument(
        "--trust-root",
        default=None,
        help="Optional aiir.trust.v1 trust root for offline checkpoint and witness verification",
    )
    parser.add_argument(
        "--witnessed-checkpoint",
        default=None,
        help="Optional raw signed checkpoint note with witness cosignatures",
    )
    parser.add_argument(
        "--require-witnesses",
        default=None,
        help="Optional witness quorum (N-of-M) or trust-root policy name",
    )
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact)
    bundle_path = Path(args.bundle)

    if args.trust_root:
        _, transparency_mod = _load_aiir_modules()
        result = transparency_mod.verify_transparency_material(
            str(artifact_path),
            str(bundle_path),
            args.trust_root,
            witnessed_checkpoint_path=args.witnessed_checkpoint,
            require_witnesses=args.require_witnesses,
        )
        if not result.get("valid"):
            print("ERROR: offline transparency verification failed", file=sys.stderr)
            return 1

        print("OK: offline transparency verification passed")
        return 0

    errors = validate_bundle(artifact_path, bundle_path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    sign_mod, _ = _load_aiir_modules()
    summary = sign_mod.summarize_sigstore_bundle(_load_json(bundle_path))
    first_entry = summary.get("entries", [{}])[0] if summary.get("entries") else {}
    detail = []
    if first_entry.get("kind"):
        detail.append(str(first_entry["kind"]))
    if first_entry.get("log_index"):
        detail.append(f"logIndex={first_entry['log_index']}")
    if first_entry.get("integrated_time_rfc3339"):
        detail.append(f"integrated={first_entry['integrated_time_rfc3339']}")

    print(
        f"OK: {bundle_path.name} matches {artifact_path.name} and passes Rekor linkage sanity checks"
        + (f" ({', '.join(detail)})" if detail else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
