#!/usr/bin/env python3
"""Run the public AIIR release evidence gate.

This wrapper keeps the public verification story simple by checking two public,
networked release-evidence surfaces:

1. Strict PEP 740 provenance coverage for every release artifact on PyPI.
2. The GitHub release attestation surface emitted as ``release-attest.json``
   and ``release-attest.md``.

The GitHub release manifest is cross-checked against the published PyPI files,
the GitHub release assets, and the uploaded ``*.intoto.jsonl`` provenance
bundles. This does not replace AIIR's local offline receipt verification.

Usage:
    python scripts/verify-release-evidence.py
    python scripts/verify-release-evidence.py 1.7.0
    python scripts/verify-release-evidence.py --verbose

Exit codes:
    0  Release evidence surfaces are complete and consistent
    1  Missing or inconsistent release evidence

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
import urllib.request


DEFAULT_REPO = "invariant-systems-ai/aiir"
GITHUB_RELEASE_URL = "https://api.github.com/repos/{repo}/releases/tags/{tag}"
HTTP_TIMEOUT = 30
RELEASE_ATTEST_JSON = "release-attest.json"
RELEASE_ATTEST_MD = "release-attest.md"
SBOM_ASSET = "aiir-sbom.cdx.json"


def _load_verify_module() -> ModuleType:
    script_path = Path(__file__).with_name("verify-pypi-provenance.py")
    spec = importlib.util.spec_from_file_location("verify_pypi_provenance", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load verifier script: {script_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_bytes(url: str, *, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.read()


def _normalize_tag(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def get_release_asset_urls(
    repo: str, version: str, *, token: str | None = None
) -> dict[str, str]:
    payload = _fetch_json(
        GITHUB_RELEASE_URL.format(repo=repo, tag=_normalize_tag(version)),
        headers=_github_headers(token),
    )
    assets = payload.get("assets", [])
    result: dict[str, str] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        download_url = asset.get("browser_download_url")
        if isinstance(name, str) and isinstance(download_url, str):
            result[name] = download_url
    return result


def verify_release_attest_manifest(
    version: str,
    verify_mod: ModuleType,
    *,
    repo: str = DEFAULT_REPO,
    verbose: bool = False,
) -> bool:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    print(
        f"Checking GitHub release attestation surface for {repo}@{_normalize_tag(version)}"
    )

    try:
        asset_urls = get_release_asset_urls(repo, version, token=token)
    except Exception as exc:
        print(f"ERROR: Could not fetch GitHub release assets: {exc}", file=sys.stderr)
        return False

    missing_assets = [
        asset_name
        for asset_name in (RELEASE_ATTEST_JSON, RELEASE_ATTEST_MD)
        if asset_name not in asset_urls
    ]
    if missing_assets:
        print(
            f"ERROR: Missing release attestation assets: {', '.join(missing_assets)}",
            file=sys.stderr,
        )
        return False

    try:
        manifest = _fetch_json(asset_urls[RELEASE_ATTEST_JSON])
    except Exception as exc:
        print(f"ERROR: Could not fetch {RELEASE_ATTEST_JSON}: {exc}", file=sys.stderr)
        return False

    if not isinstance(manifest, list):
        print(
            f"ERROR: {RELEASE_ATTEST_JSON} must be a JSON array of artifact rows",
            file=sys.stderr,
        )
        return False

    try:
        release_files = verify_mod.get_release_files(version)
    except Exception as exc:
        print(f"ERROR: Could not fetch PyPI release files: {exc}", file=sys.stderr)
        return False

    expected_files = {
        str(file_info.get("filename")): file_info
        for file_info in release_files
        if isinstance(file_info, dict) and isinstance(file_info.get("filename"), str)
    }
    sbom_asset_url = asset_urls.get(SBOM_ASSET, "")
    if not sbom_asset_url:
        print(f"ERROR: Missing GitHub release asset: {SBOM_ASSET}", file=sys.stderr)
        return False

    rows_by_artifact: dict[str, dict[str, Any]] = {}
    ok = True

    for row in manifest:
        if not isinstance(row, dict):
            print(
                "ERROR: release-attest.json contains a non-object row", file=sys.stderr
            )
            ok = False
            continue
        artifact = row.get("artifact")
        if not isinstance(artifact, str) or not artifact:
            print(
                "ERROR: release-attest.json row is missing a valid artifact name",
                file=sys.stderr,
            )
            ok = False
            continue
        if artifact in rows_by_artifact:
            print(
                f"ERROR: duplicate release-attest row for {artifact}", file=sys.stderr
            )
            ok = False
            continue
        rows_by_artifact[artifact] = row

    expected_rows = set(expected_files)
    expected_rows.add(SBOM_ASSET)

    extras = sorted(set(rows_by_artifact) - expected_rows)
    if extras:
        print(
            f"ERROR: release-attest.json has unexpected artifact rows: {', '.join(extras)}",
            file=sys.stderr,
        )
        ok = False

    if len(rows_by_artifact) != len(expected_rows):
        print(
            "ERROR: release-attest.json row count does not match expected release assets",
            file=sys.stderr,
        )
        ok = False

    for filename, file_info in expected_files.items():
        row = rows_by_artifact.get(filename)
        if row is None:
            print(
                f"ERROR: release-attest.json missing row for {filename}",
                file=sys.stderr,
            )
            ok = False
            continue
        row_kind = str(row.get("kind") or "")
        if row_kind and row_kind != "distribution":
            print(
                f"ERROR: {filename} row kind must be 'distribution'",
                file=sys.stderr,
            )
            ok = False

        expected_sha256 = str(file_info.get("digests", {}).get("sha256") or "")
        expected_pypi_url = verify_mod.PYPI_INTEGRITY_URL.format(
            project=verify_mod.PYPI_PROJECT,
            version=version,
            filename=filename,
        )
        expected_pypi_file_url = str(file_info.get("url") or "")
        expected_github_bundle = f"{filename}.intoto.jsonl"
        expected_release_asset_url = asset_urls.get(filename, "")
        expected_bundle_url = asset_urls.get(expected_github_bundle, "")

        checks = [
            ("sha256", expected_sha256),
            ("pypi_attestation_url", expected_pypi_url),
            ("pypi_file_url", expected_pypi_file_url),
            ("github_provenance_asset", expected_github_bundle),
            ("github_release_asset_url", expected_release_asset_url),
            ("github_provenance_asset_url", expected_bundle_url),
        ]
        for field_name, expected_value in checks:
            if str(row.get(field_name) or "") != expected_value:
                print(
                    f"ERROR: {filename} field {field_name} did not match expected release evidence",
                    file=sys.stderr,
                )
                ok = False

        rekor_entries = row.get("rekor_entries")
        if not isinstance(rekor_entries, list) or not rekor_entries:
            print(f"ERROR: {filename} is missing Rekor log entries", file=sys.stderr)
            ok = False
        else:
            for entry in rekor_entries:
                if not isinstance(entry, dict) or not str(entry.get("log_index") or ""):
                    print(
                        f"ERROR: {filename} has an invalid Rekor entry in release-attest.json",
                        file=sys.stderr,
                    )
                    ok = False
                    break

        if verbose:
            print(json.dumps(row, indent=2))

    sbom_row = rows_by_artifact.get(SBOM_ASSET)
    if sbom_row is None:
        print(
            f"ERROR: release-attest.json missing row for {SBOM_ASSET}", file=sys.stderr
        )
        ok = False
    else:
        row_kind = str(sbom_row.get("kind") or "")
        if row_kind != "sbom":
            print(
                f"ERROR: {SBOM_ASSET} row kind must be 'sbom'",
                file=sys.stderr,
            )
            ok = False
        try:
            sbom_sha256 = hashlib.sha256(
                _fetch_bytes(sbom_asset_url, headers=_github_headers(token))
            ).hexdigest()
        except Exception as exc:
            print(f"ERROR: Could not fetch {SBOM_ASSET}: {exc}", file=sys.stderr)
            return False

        sbom_checks = [
            ("sha256", sbom_sha256),
            ("github_release_asset_url", sbom_asset_url),
            ("github_provenance_asset", ""),
            ("github_provenance_asset_url", ""),
            ("pypi_attestation_url", ""),
            ("pypi_file_url", ""),
        ]
        for field_name, expected_value in sbom_checks:
            if str(sbom_row.get(field_name) or "") != expected_value:
                print(
                    f"ERROR: {SBOM_ASSET} field {field_name} did not match expected release evidence",
                    file=sys.stderr,
                )
                ok = False

        rekor_entries = sbom_row.get("rekor_entries")
        if not isinstance(rekor_entries, list):
            print(
                f"ERROR: {SBOM_ASSET} must carry a list for rekor_entries",
                file=sys.stderr,
            )
            ok = False

        if verbose:
            print(json.dumps(sbom_row, indent=2))

    if ok:
        print("GitHub release attestation surface is complete.")
    return ok


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify published AIIR release evidence via the PyPI Integrity API and "
            "the GitHub release attestation surface. This is the public release gate, "
            "not an offline verifier."
        )
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="AIIR version to verify. Defaults to the latest published version.",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository to inspect (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed release evidence rows while verifying.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    mod = _load_verify_module()
    version = args.version or mod.get_latest_version()

    print("AIIR release evidence gate")
    print("Checks published PEP 740 attestation coverage for every release artifact.")
    print(
        "Checks GitHub release-attest assets, the SBOM asset, and their bindings to PyPI + GitHub bundles."
    )
    print("For local offline receipt verification, use: aiir --verify <receipt>")
    print()

    pypi_ok = mod.verify_release(version, strict=True, verbose=args.verbose)
    print()
    release_ok = verify_release_attest_manifest(
        version,
        mod,
        repo=args.repo,
        verbose=args.verbose,
    )
    return 0 if pypi_ok and release_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
