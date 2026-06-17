#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PYPI_JSON_URL = "https://pypi.org/pypi/{project}/{version}/json"
PYPI_INTEGRITY_URL = (
    "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
)
HTTP_TIMEOUT = 30
EXPECTED_PREDICATE_TYPES = {
    "https://docs.pypi.org/attestations/publish/v1",
}


def fetch_json(url: str) -> tuple[Any | None, int]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.pypi.integrity.v1+json, application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urllib.error.HTTPError as exc:
        return None, exc.code
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None, 0


def fetch_json_retry(
    url: str, *, retries: int, delay_seconds: int
) -> tuple[Any | None, int]:
    last_data: Any | None = None
    last_status = 0
    for attempt in range(retries):
        last_data, last_status = fetch_json(url)
        if last_status == 200:
            return last_data, last_status
        if attempt + 1 < retries:
            time.sleep(delay_seconds)
    return last_data, last_status


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        destination.write_bytes(response.read())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def decode_statement(encoded: str) -> dict[str, Any]:
    return json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))


def load_release_files(project: str, version: str) -> list[dict[str, Any]]:
    data, status = fetch_json(PYPI_JSON_URL.format(project=project, version=version))
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(
            f"Could not fetch PyPI metadata for {project}=={version} (HTTP {status})"
        )
    files = data.get("urls", [])
    if not isinstance(files, list) or not files:
        raise RuntimeError(f"No release files found for {project}=={version}")
    return files


def enforce_file(
    *,
    project: str,
    version: str,
    file_info: dict[str, Any],
    out_dir: Path,
    expected_repository: str,
    expected_workflow: str,
    expected_environment: str,
    retries: int,
    delay_seconds: int,
) -> dict[str, Any]:
    filename = file_info["filename"]
    artifact_path = out_dir / filename
    download(file_info["url"], artifact_path)
    actual_digest = sha256_file(artifact_path)
    expected_digest = file_info.get("digests", {}).get("sha256", "")
    if actual_digest != expected_digest:
        raise RuntimeError(
            f"Digest mismatch for {filename}: expected {expected_digest}, got {actual_digest}"
        )

    provenance_url = PYPI_INTEGRITY_URL.format(
        project=project, version=version, filename=filename
    )
    provenance, status = fetch_json_retry(
        provenance_url,
        retries=retries,
        delay_seconds=delay_seconds,
    )
    if status != 200 or not isinstance(provenance, dict):
        raise RuntimeError(
            f"Integrity API did not return provenance for {filename} (HTTP {status})"
        )

    bundles = provenance.get("attestation_bundles", [])
    if not isinstance(bundles, list) or not bundles:
        raise RuntimeError(f"No attestation bundles found for {filename}")

    seen_predicates: set[str] = set()
    matched_statement = False
    publisher_matches = False

    for bundle in bundles:
        publisher = bundle.get("publisher", {})
        if (
            publisher.get("kind") == "GitHub"
            and publisher.get("repository") == expected_repository
            and publisher.get("workflow") == expected_workflow
            and publisher.get("environment") == expected_environment
        ):
            publisher_matches = True

        attestations = bundle.get("attestations", [])
        if not isinstance(attestations, list):
            continue
        for attestation in attestations:
            statement = decode_statement(attestation["envelope"]["statement"])
            seen_predicates.add(statement.get("predicateType", ""))
            subject = (statement.get("subject") or [{}])[0]
            if (
                subject.get("name") == filename
                and subject.get("digest", {}).get("sha256") == actual_digest
            ):
                matched_statement = True

    if not publisher_matches:
        raise RuntimeError(
            f"Publisher policy mismatch for {filename}: expected GitHub/{expected_repository}/{expected_workflow}/{expected_environment}"
        )

    if not matched_statement:
        raise RuntimeError(
            f"No attestation statement in provenance matches {filename} with digest {actual_digest}"
        )

    missing_predicates = sorted(EXPECTED_PREDICATE_TYPES - seen_predicates)
    if missing_predicates:
        raise RuntimeError(
            f"Missing expected predicate types for {filename}: {', '.join(missing_predicates)}"
        )

    return {
        "filename": filename,
        "sha256": actual_digest,
        "provenance_url": provenance_url,
        "predicate_types": sorted(seen_predicates),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce strict PyPI provenance policy for a release.",
    )
    parser.add_argument("version", help="Version on PyPI to verify")
    parser.add_argument("--project", default="aiir")
    parser.add_argument("--repository", default="invariant-systems-ai/aiir")
    parser.add_argument("--workflow", default="publish.yml")
    parser.add_argument("--environment", default="pypi")
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--delay-seconds", type=int, default=20)
    parser.add_argument("--out-dir", default="/tmp/aiir-pypi-provenance")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = load_release_files(args.project, args.version)
    results = []
    for file_info in files:
        results.append(
            enforce_file(
                project=args.project,
                version=args.version,
                file_info=file_info,
                out_dir=out_dir,
                expected_repository=args.repository,
                expected_workflow=args.workflow,
                expected_environment=args.environment,
                retries=args.retries,
                delay_seconds=args.delay_seconds,
            )
        )

    print(
        json.dumps(
            {"project": args.project, "version": args.version, "files": results},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
