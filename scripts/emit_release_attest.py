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


PYPI_JSON_URL = "https://pypi.org/pypi/{project}/{version}/json"
PYPI_INTEGRITY_URL = (
    "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
)
GITHUB_RELEASE_URL = "https://api.github.com/repos/{repo}/releases/tags/{tag}"
GITHUB_ATTESTATION_URL = (
    "https://api.github.com/repos/{repo}/attestations/sha256:{digest}"
)
HTTP_TIMEOUT = 30
BEGIN_MARKER = "<!-- BEGIN:RELEASE_ATTESTATION -->"
END_MARKER = "<!-- END:RELEASE_ATTESTATION -->"
SBOM_ASSET_NAME = "aiir-sbom.cdx.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def strip_v_prefix(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_json_safe(
    url: str, *, headers: dict[str, str] | None = None
) -> tuple[dict[str, Any] | None, int]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8")), response.status
    except urllib.error.HTTPError as exc:
        return None, exc.code
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None, 0


def load_release_assets(
    repo: str, tag: str, *, token: str | None = None
) -> dict[str, str]:
    payload = _fetch_json(
        GITHUB_RELEASE_URL.format(repo=repo, tag=tag),
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


def load_pypi_release_files(project: str, version: str) -> list[dict[str, Any]]:
    payload = _fetch_json(PYPI_JSON_URL.format(project=project, version=version))
    files = payload.get("urls", [])
    return [item for item in files if isinstance(item, dict)]


def build_pypi_provenance_url(project: str, version: str, filename: str) -> str:
    return PYPI_INTEGRITY_URL.format(
        project=project,
        version=version,
        filename=filename,
    )


def fetch_attestation_bundle(
    repo: str, digest: str, *, token: str | None = None
) -> dict[str, Any]:
    payload = _fetch_json(
        GITHUB_ATTESTATION_URL.format(repo=repo, digest=digest),
        headers=_github_headers(token),
    )
    attestations = payload.get("attestations", [])
    if not isinstance(attestations, list) or not attestations:
        raise RuntimeError(f"No GitHub attestations found for sha256:{digest}")
    bundle = attestations[0].get("bundle")
    if not isinstance(bundle, dict):
        raise RuntimeError(f"Malformed GitHub attestation bundle for sha256:{digest}")
    return bundle


def extract_tlog_entries(bundle: dict[str, Any]) -> list[dict[str, str]]:
    verification_material = bundle.get("verificationMaterial")
    if not isinstance(verification_material, dict):
        return []
    tlog_entries = verification_material.get("tlogEntries")
    if not isinstance(tlog_entries, list):
        return []

    rows: list[dict[str, str]] = []
    for entry in tlog_entries:
        if not isinstance(entry, dict):
            continue
        log_index = str(entry.get("logIndex") or "")
        integrated_time = str(entry.get("integratedTime") or "")
        log_id = ""
        log_id_block = entry.get("logId")
        if isinstance(log_id_block, dict):
            log_id = str(log_id_block.get("keyId") or "")
        kind = ""
        kind_block = entry.get("kindVersion")
        if isinstance(kind_block, dict):
            kind = str(kind_block.get("kind") or "")
        rows.append(
            {
                "log_index": log_index,
                "integrated_time": integrated_time,
                "log_id": log_id,
                "kind": kind,
            }
        )
    return rows


def build_release_attestation_rows(
    *,
    repo: str,
    tag: str,
    project: str,
    dist_dir: Path,
    sbom_path: Path | None = None,
    token: str | None = None,
) -> list[dict[str, Any]]:
    version = strip_v_prefix(tag)
    release_assets = load_release_assets(repo, tag, token=token)
    pypi_files = {
        str(item.get("filename")): item
        for item in load_pypi_release_files(project, version)
        if isinstance(item.get("filename"), str)
    }

    rows: list[dict[str, Any]] = []
    for artifact_path in sorted(path for path in dist_dir.iterdir() if path.is_file()):
        digest = sha256_file(artifact_path)
        filename = artifact_path.name
        bundle = fetch_attestation_bundle(repo, digest, token=token)
        tlog_entries = extract_tlog_entries(bundle)
        provenance_asset_name = f"{filename}.intoto.jsonl"
        pypi_info = pypi_files.get(filename, {})
        rows.append(
            {
                "kind": "distribution",
                "artifact": filename,
                "sha256": digest,
                "github_release_asset_url": release_assets.get(filename, ""),
                "github_provenance_asset": provenance_asset_name,
                "github_provenance_asset_url": release_assets.get(
                    provenance_asset_name, ""
                ),
                "pypi_attestation_url": build_pypi_provenance_url(
                    project, version, filename
                ),
                "pypi_file_url": str(pypi_info.get("url") or ""),
                "rekor_entries": tlog_entries,
            }
        )

    if sbom_path is not None:
        rows.append(
            {
                "kind": "sbom",
                "artifact": sbom_path.name,
                "sha256": sha256_file(sbom_path),
                "github_release_asset_url": release_assets.get(sbom_path.name, ""),
                "github_provenance_asset": "",
                "github_provenance_asset_url": "",
                "pypi_attestation_url": "",
                "pypi_file_url": "",
                "rekor_entries": [],
            }
        )
    return rows


def render_markdown(rows: list[dict[str, Any]], *, project: str, tag: str) -> str:
    version = strip_v_prefix(tag)
    lines = [
        BEGIN_MARKER,
        "## Provenance & Verification",
        "",
        "| Artifact | SHA-256 | Rekor log index | Provenance |",
        "|---|---|---|---|",
    ]

    for row in rows:
        artifact_label = row["artifact"]
        artifact_url = row.get("github_release_asset_url") or row.get("pypi_file_url")
        if artifact_url:
            artifact_cell = f"[{artifact_label}]({artifact_url})"
        else:
            artifact_cell = f"`{artifact_label}`"

        rekor_entries = row.get("rekor_entries") or []
        rekor_cell = " - "
        if rekor_entries:
            rekor_cell = (
                ", ".join(
                    f"`{entry.get('log_index', '')}`"
                    for entry in rekor_entries
                    if entry.get("log_index")
                )
                or " - "
            )

        provenance_links: list[str] = []
        if row.get("pypi_attestation_url"):
            provenance_links.append(
                f"[PyPI attestation]({row['pypi_attestation_url']})"
            )
        if row.get("github_provenance_asset_url"):
            provenance_links.append(
                f"[GitHub bundle]({row['github_provenance_asset_url']})"
            )
        if not provenance_links and artifact_url:
            provenance_links.append(f"[GitHub release asset]({artifact_url})")
        provenance_cell = " · ".join(provenance_links)

        lines.append(
            f"| {artifact_cell} | `sha256:{row['sha256']}` | {rekor_cell} | {provenance_cell} |"
        )

    lines.extend(
        [
            "",
            "```bash",
            f"# Verify the published release evidence for {project}=={version}",
            f"python scripts/verify-release-evidence.py {version}",
            "```",
            END_MARKER,
        ]
    )
    return "\n".join(lines) + "\n"


def upsert_marked_section(body: str, section: str) -> str:
    if BEGIN_MARKER in body and END_MARKER in body:
        before, remainder = body.split(BEGIN_MARKER, 1)
        _, after = remainder.split(END_MARKER, 1)
        prefix = before.rstrip()
        suffix = after.lstrip("\n")
        pieces = [
            piece for piece in (prefix, section.rstrip(), suffix.rstrip()) if piece
        ]
        return "\n\n".join(pieces) + "\n"

    body = body.rstrip()
    if not body:
        return section
    return body + "\n\n" + section


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit a release-facing provenance surface for GitHub releases.",
    )
    parser.add_argument("--repo", required=True, help="GitHub repo, e.g. owner/name")
    parser.add_argument("--tag", required=True, help="Release tag, e.g. v1.3.0")
    parser.add_argument("--project", default="aiir", help="PyPI project name")
    parser.add_argument(
        "--dist-dir", default="dist", help="Directory containing built artifacts"
    )
    parser.add_argument(
        "--sbom-path",
        default="",
        help=f"Optional path to {SBOM_ASSET_NAME} for explicit release-surface coverage",
    )
    parser.add_argument("--json-out", default="release-attest.json")
    parser.add_argument("--md-out", default="release-attest.md")
    parser.add_argument(
        "--release-body-out",
        default="",
        help="Optional path for an updated GitHub release body containing the attestation section",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_dir():
        raise SystemExit(f"dist dir not found: {dist_dir}")

    sbom_path: Path | None = None
    if args.sbom_path:
        sbom_path = Path(args.sbom_path)
        if not sbom_path.is_file():
            raise SystemExit(f"sbom file not found: {sbom_path}")

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    rows = build_release_attestation_rows(
        repo=args.repo,
        tag=args.tag,
        project=args.project,
        dist_dir=dist_dir,
        sbom_path=sbom_path,
        token=token,
    )
    markdown = render_markdown(rows, project=args.project, tag=args.tag)

    write_text(Path(args.json_out), json.dumps(rows, indent=2) + "\n")
    write_text(Path(args.md_out), markdown)

    if args.release_body_out:
        release = _fetch_json(
            GITHUB_RELEASE_URL.format(repo=args.repo, tag=args.tag),
            headers=_github_headers(token),
        )
        existing_body = str(release.get("body") or "")
        updated = upsert_marked_section(existing_body, markdown)
        write_text(Path(args.release_body_out), updated)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
