#!/usr/bin/env python3
"""Sync AIIR automation secrets from a canonical local vault into GitHub Actions.

Copyright 2025-2026 Invariant Systems, Inc.
# SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / ".github" / "automation-secrets.json"


@dataclass(frozen=True)
class SecretEntry:
    name: str
    sources: tuple[str, ...]
    required: bool
    description: str


def load_catalog(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_env_stream(payload: bytes) -> dict[str, str]:
    env_map: dict[str, str] = {}
    for chunk in payload.split(b"\0"):
        if not chunk or b"=" not in chunk:
            continue
        key_bytes, value_bytes = chunk.split(b"=", 1)
        env_map[key_bytes.decode("utf-8", "ignore")] = value_bytes.decode(
            "utf-8", "ignore"
        )
    return env_map


def load_vault_env(vault_file: Path) -> dict[str, str]:
    if not vault_file.exists():
        return {}
    bash = shutil.which("bash")
    if bash is None:
        raise RuntimeError("bash is required to source the canonical vault file")
    command = f"set -a; source {shlex.quote(str(vault_file))}; env -0"
    completed = subprocess.run(
        [bash, "-lc", command],
        check=True,
        capture_output=True,
    )
    return parse_env_stream(completed.stdout)


def combine_env(vault_env: dict[str, str]) -> dict[str, str]:
    combined = dict(vault_env)
    for key, value in os.environ.items():
        if value:
            combined[key] = value
    return combined


def build_entries(catalog: dict) -> list[SecretEntry]:
    return [
        SecretEntry(
            name=item["name"],
            sources=tuple(item["sources"]),
            required=bool(item.get("required", True)),
            description=item.get("description", ""),
        )
        for item in catalog["entries"]
    ]


def filter_entries(
    entries: Iterable[SecretEntry], selected: set[str]
) -> list[SecretEntry]:
    if not selected:
        return list(entries)
    return [entry for entry in entries if entry.name in selected]


def resolve_secret_source(entry: SecretEntry, env_map: dict[str, str]) -> str | None:
    for source in entry.sources:
        if env_map.get(source, ""):
            return source
    return None


def run_command(argv: list[str], body: str | None = None) -> None:
    subprocess.run(argv, input=body, text=True, check=True)


def ensure_environment(repo: str, environment: str) -> None:
    run_command(
        ["gh", "api", "--method", "PUT", f"repos/{repo}/environments/{environment}"]
    )


def set_environment_secret(repo: str, environment: str, name: str, value: str) -> None:
    run_command(
        [
            "gh",
            "secret",
            "set",
            name,
            "--repo",
            repo,
            "--env",
            environment,
            "--body",
            value,
        ]
    )


def set_repo_secret(repo: str, name: str, value: str) -> None:
    run_command(["gh", "secret", "set", name, "--repo", repo, "--body", value])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--vault-file", type=Path, help="Override the canonical vault file path"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check canonical-vault coverage without writing any secrets (default mode)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write secrets into GitHub Actions"
    )
    parser.add_argument(
        "--secret",
        dest="secrets",
        action="append",
        default=[],
        help="Restrict sync/check to one or more named secrets",
    )
    parser.add_argument(
        "--sync-repo-bridge",
        action="store_true",
        help="Also sync compatibility repo-level secrets defined in the catalog",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.check and args.apply:
        raise SystemExit("--check and --apply are mutually exclusive")
    catalog = load_catalog(args.config)
    github = catalog["github"]
    environment_name = github["environment"]
    repo = github["repo"]
    vault_file = args.vault_file or Path(catalog["vault_file"]).expanduser()
    entries = filter_entries(build_entries(catalog), set(args.secrets))
    env_map = combine_env(load_vault_env(vault_file))

    resolved_values: dict[str, str] = {}
    missing_required: list[str] = []

    for entry in entries:
        source = resolve_secret_source(entry, env_map)
        if source is None:
            status = "MISSING" if entry.required else "OPTIONAL"
            print(
                f"{status:8} {entry.name:<22} sources={','.join(entry.sources)} description={entry.description}"
            )
            if entry.required:
                missing_required.append(entry.name)
            continue
        print(f"READY    {entry.name:<22} target=github:{repo}:{environment_name}")
        resolved_values[entry.name] = env_map[source]

    if args.apply:
        ensure_environment(repo, environment_name)
        for entry in entries:
            value = resolved_values.get(entry.name)
            if value is None:
                continue
            set_environment_secret(repo, environment_name, entry.name, value)
            print(f"SYNCED   {entry.name:<22} environment={environment_name}")

        if args.sync_repo_bridge:
            bridge_entries = set(catalog.get("repo_bridge_entries", []))
            for entry in entries:
                if entry.name not in bridge_entries:
                    continue
                value = resolved_values.get(entry.name)
                if value is None:
                    continue
                set_repo_secret(repo, entry.name, value)
                print(f"BRIDGED  {entry.name:<22} scope=repo")

    return 1 if missing_required else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
