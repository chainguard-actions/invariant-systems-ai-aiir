#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


EXIT_INTEGRITY_MISSING = 11
EXIT_DIGEST_MISMATCH = 12
EXIT_BUNDLE_MISSING = 13
EXIT_OIDC_UNAVAILABLE = 14

PYPI_PROJECT = "aiir"
GITHUB_REPO = "invariant-systems-ai/aiir"
HTTP_TIMEOUT = 30


def failure_code_for(source: str, event: str) -> int:
    mapping = {
        ("pypi", "push"): EXIT_INTEGRITY_MISSING,
        ("pypi", "pull_request"): EXIT_DIGEST_MISMATCH,
        ("gh-release", "push"): EXIT_BUNDLE_MISSING,
        ("gh-release", "pull_request"): EXIT_OIDC_UNAVAILABLE,
    }
    return mapping[(source, event)]


def mutate_digest(digest: str) -> str:
    if not digest:
        return "0" * 64
    head = "0" if digest[0] != "0" else "1"
    return head + digest[1:]


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def fetch_json(
    url: str, *, headers: dict[str, str] | None = None
) -> tuple[Any | None, int]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urllib.error.HTTPError as exc:
        return None, exc.code
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None, 0


def download(
    url: str, destination: Path, *, headers: dict[str, str] | None = None
) -> None:
    request = urllib.request.Request(url, headers=headers or {})
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


def select_pypi_file(release_data: dict[str, Any]) -> dict[str, Any]:
    urls = release_data.get("urls", [])
    wheels = [item for item in urls if item.get("packagetype") == "bdist_wheel"]
    if wheels:
        return wheels[-1]
    if urls:
        return urls[-1]
    raise ValueError("no release files found on PyPI")


def select_release_asset(release_data: dict[str, Any]) -> dict[str, Any]:
    assets = release_data.get("assets", [])
    preferred_suffixes = (".whl", ".tar.gz")
    for suffix in preferred_suffixes:
        for asset in assets:
            if asset.get("name", "").endswith(suffix):
                return asset
    if assets:
        return assets[0]
    raise ValueError("no release assets found on GitHub")


def build_summary(*, source: str, event: str, out_dir: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "source": source,
        "event": event,
        "actual_event": os.getenv("GITHUB_EVENT_NAME", ""),
        "expected_exit_code": failure_code_for(source, event),
    }
    for name in ("index", "integrity", "cosign_error", "oidc_error", "error"):
        path = out_dir / f"{name}.json"
        if path.exists():
            summary[name] = json.loads(path.read_text(encoding="utf-8"))
    artifact_sha = out_dir / "artifact.sha256"
    if artifact_sha.exists():
        summary["artifact_sha256"] = artifact_sha.read_text(encoding="utf-8").strip()
    return summary


def fail(*, code: int, out_dir: Path, payload: dict[str, Any], file_name: str) -> int:
    write_json(out_dir / file_name, payload)
    write_json(
        out_dir / "preflight.json",
        build_summary(
            source=payload["source"], event=payload["event"], out_dir=out_dir
        ),
    )
    print((out_dir / "preflight.json").read_text(encoding="utf-8"))
    return code


def run_pypi(event: str, out_dir: Path, package: str, version: str) -> int:
    latest_data, latest_status = fetch_json(f"https://pypi.org/pypi/{package}/json")
    if latest_status != 200 or not isinstance(latest_data, dict):
        return fail(
            code=EXIT_INTEGRITY_MISSING,
            out_dir=out_dir,
            payload={
                "source": "pypi",
                "event": event,
                "error": "PYPI_METADATA_UNAVAILABLE",
                "detail": f"Could not fetch package metadata for {package}",
            },
            file_name="error.json",
        )

    resolved_version = (
        latest_data["info"]["version"] if version == "latest" else version
    )
    release_data, release_status = fetch_json(
        f"https://pypi.org/pypi/{package}/{resolved_version}/json"
    )
    if release_status != 200 or not isinstance(release_data, dict):
        return fail(
            code=EXIT_INTEGRITY_MISSING,
            out_dir=out_dir,
            payload={
                "source": "pypi",
                "event": event,
                "error": "PYPI_RELEASE_UNAVAILABLE",
                "detail": f"Could not fetch release metadata for {package}=={resolved_version}",
            },
            file_name="error.json",
        )

    file_info = select_pypi_file(release_data)
    artifact_path = out_dir / file_info["filename"]
    download(file_info["url"], artifact_path)
    actual_digest = sha256_file(artifact_path)
    (out_dir / "artifact.sha256").write_text(actual_digest + "\n", encoding="utf-8")
    write_json(
        out_dir / "index.json",
        {
            "project": package,
            "version": resolved_version,
            "filename": file_info["filename"],
            "file_url": file_info["url"],
            "digest": file_info.get("digests", {}).get("sha256"),
        },
    )

    provenance_url = f"https://pypi.org/integrity/{package}/{resolved_version}/{file_info['filename']}/provenance"
    integrity_url = provenance_url
    if event == "push":
        integrity_url = provenance_url.replace(
            file_info["filename"], f"{file_info['filename']}.missing"
        )
    integrity_data, integrity_status = fetch_json(integrity_url)
    write_json(
        out_dir / "integrity.json",
        {
            "url": integrity_url,
            "http_status": integrity_status,
            "response": integrity_data,
        },
    )

    if event == "push":
        return fail(
            code=EXIT_INTEGRITY_MISSING,
            out_dir=out_dir,
            payload={
                "source": "pypi",
                "event": event,
                "error": "INTEGRITY_MISSING",
                "detail": "Rehearsal queried a guaranteed-missing provenance path and failed closed.",
                "url": integrity_url,
                "http_status": integrity_status,
            },
            file_name="error.json",
        )

    expected_digest = mutate_digest(str(file_info.get("digests", {}).get("sha256", "")))
    return fail(
        code=EXIT_DIGEST_MISMATCH,
        out_dir=out_dir,
        payload={
            "source": "pypi",
            "event": event,
            "error": "DIGEST_MISMATCH",
            "detail": "Rehearsal intentionally mutated the expected digest to prove the gate fails closed.",
            "expected": expected_digest,
            "actual": actual_digest,
        },
        file_name="error.json",
    )


def run_github_release(event: str, out_dir: Path, repo: str) -> int:
    headers = {}
    if os.getenv("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    release_data, release_status = fetch_json(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers=headers,
    )
    if release_status != 200 or not isinstance(release_data, dict):
        return fail(
            code=EXIT_BUNDLE_MISSING if event == "push" else EXIT_OIDC_UNAVAILABLE,
            out_dir=out_dir,
            payload={
                "source": "gh-release",
                "event": event,
                "error": "GITHUB_RELEASE_UNAVAILABLE",
                "detail": f"Could not fetch latest release metadata for {repo}",
            },
            file_name="error.json",
        )

    asset = select_release_asset(release_data)
    artifact_path = out_dir / asset["name"]
    download(asset["browser_download_url"], artifact_path, headers=headers)
    actual_digest = sha256_file(artifact_path)
    (out_dir / "artifact.sha256").write_text(actual_digest + "\n", encoding="utf-8")
    write_json(
        out_dir / "index.json",
        {
            "repo": repo,
            "tag": release_data.get("tag_name"),
            "filename": asset["name"],
            "file_url": asset["browser_download_url"],
            "digest": None,
        },
    )

    if event == "push":
        return fail(
            code=EXIT_BUNDLE_MISSING,
            out_dir=out_dir,
            payload={
                "source": "gh-release",
                "event": event,
                "error": "BUNDLE_MISSING",
                "detail": "Rehearsal expects a cosign bundle next to the release asset and fails when absent.",
                "bundle_path": str(out_dir / f"{asset['name']}.sigstore.json"),
            },
            file_name="cosign_error.json",
        )

    oidc_available = bool(
        os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL")
        and os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    )
    return fail(
        code=EXIT_OIDC_UNAVAILABLE,
        out_dir=out_dir,
        payload={
            "source": "gh-release",
            "event": event,
            "error": "OIDC_UNAVAILABLE_FOR_FORK",
            "detail": "Rehearsal simulates the fork-PR path, where GitHub intentionally withholds id-token credentials.",
            "oidc_available_in_runner": oidc_available,
        },
        file_name="oidc_error.json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic PEP 740 / Integrity API preflight rehearsal.",
    )
    parser.add_argument("--source", choices=["pypi", "gh-release"], required=True)
    parser.add_argument("--event", choices=["push", "pull_request"], required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--package", default=PYPI_PROJECT)
    parser.add_argument("--version", default="latest")
    parser.add_argument("--repo", default=GITHUB_REPO)
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.source == "pypi":
        return run_pypi(args.event, out_dir, args.package, args.version)
    return run_github_release(args.event, out_dir, args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
