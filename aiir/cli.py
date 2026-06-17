#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR — AI Integrity Receipts

Generate cryptographic receipts for git commits. Detects AI authorship signals
(Copilot, ChatGPT, Claude, Cursor, Aider, etc.) and produces content-addressed
JSON receipts suitable for audit trails and compliance.

Zero dependencies — uses only Python standard library.

This module is the public API surface and CLI entry point.
Implementation is split across _core, _detect, _receipt, _ledger,
_stats, _github, _verify, and _sign submodules.  All symbols are
re-exported here for backward compatibility.
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, NoReturn, Optional, Sequence
from urllib.parse import urlunparse  # noqa: F401 — used by tests (cli_mod.urlunparse)

# ---------------------------------------------------------------------------
# Re-export everything from submodules so that existing imports such as
#     import aiir.cli as cli; cli.detect_ai_signals(...)
# and
#     from aiir.cli import generate_receipt, verify_receipt_file
# continue to work without changes.
# ---------------------------------------------------------------------------

from aiir._core import (  # noqa: F401
    RECEIPT_SCHEMA_VERSION,
    CLI_VERSION,
    MAX_RECEIPTS_PER_RANGE,
    MAX_RECEIPT_FILE_SIZE,
    MAX_SUMMARY_SIZE,
    LEDGER_DIR as _LEDGER_DIR,
    GIT_TIMEOUT,
    _GIT_SAFE_ENV,
    _EMOJI,
    _BOX,
    _can_encode,
    _USE_EMOJI,
    _USE_BOXDRAW,
    _e,
    _b,
    _HAS_FCHMOD,
    _validate_ref,
    _sanitize_md,
    CommitInfo,
    _strip_terminal_escapes,
    _run_git,
    _sha256,
    _canonical_json,
    _MAX_JSON_DEPTH,
    _check_json_depth,
    _hash_diff_streaming,
    _strip_url_credentials,
    _now_rfc3339,
    get_repo_root,
    _normalize_for_detection,
    logger,
)

from aiir._detect import (  # noqa: F401
    AI_SIGNALS,
    AI_TRAILERS,
    detect_ai_signals,
    get_commit_info,
    list_commits_in_range,
)

from aiir._receipt import (  # noqa: F401
    build_commit_receipt,
    generate_receipt,
    generate_receipts_for_range,
    format_receipt_pretty,
    format_receipt_detail,
    write_receipt,
    wrap_in_toto_statement,
    build_review_receipt,
    REVIEW_RECEIPT_SCHEMA_VERSION,
    INTOTO_PREDICATE_TYPE,
)
from aiir._commitment import (  # noqa: F401
    build_commitment_path_artifact,
    build_commitment_receipt,
    parse_commitment_digest_spec,
)

from aiir._ledger import (  # noqa: F401
    _ledger_paths,
    _config_path,
    _load_config,
    _save_config,
    _load_index,
    _receipt_is_signed,
    _save_index,
    append_to_ledger,
    export_ledger,
)

from aiir._evidence import (  # noqa: F401
    get_receipt_evidence_tier,
    import_evidence_stream,
    normalize_receipt_to_evidence,
    summarize_evidence_stream,
)

from aiir._stats import (  # noqa: F401
    format_badge,
    format_stats,
    check_policy,
)

from aiir._policy import (  # noqa: F401
    POLICY_PRESETS,
    load_policy,
    save_policy,
    init_policy,
    evaluate_receipt_policy,
    evaluate_ledger_policy,
    format_policy_report,
)

from aiir._github import (  # noqa: F401
    set_github_output,
    set_github_summary,
    format_github_summary,
    create_check_run,
    post_pr_comment,
    format_commit_trailer,
)

from aiir._gitlab import (  # noqa: F401
    set_gitlab_ci_output,
    format_gitlab_summary,
    format_gl_sast_report,
    post_mr_comment,
    enforce_approval_rules,
    parse_webhook_event,
    validate_webhook_token,
    build_receipts_graphql_query,
    query_gitlab_graphql,
    generate_dashboard_html,
)

from aiir._verify import (  # noqa: F401
    verify_receipt,
    verify_receipt_file,
    verify_receipt_ledger_file,
)

from aiir._explain import (  # noqa: F401
    explain_verification,
)

from aiir._verify_release import (  # noqa: F401
    _load_receipts_from_ledger,
    verify_release,
    format_release_report,
    VSA_PREDICATE_TYPE,
)

from aiir._transparency import (  # noqa: F401
    verify_transparency_material,
)

from aiir._editor_provenance import consume_editor_provenance

from aiir._sign import (  # noqa: F401
    _sigstore_available,
    sign_receipt,
    sign_receipt_file,
    verify_receipt_signature,
)

# ---------------------------------------------------------------------------
# Override _e / _b so they read _USE_EMOJI / _USE_BOXDRAW from THIS module's
# globals.  Tests toggle  cli._USE_EMOJI = False  and expect  cli._e("ok")
# to return ASCII.  The originals in _core read _core._USE_EMOJI, so a
# rebind on cli wouldn't propagate.  Defining the wrappers here fixes that.
# ---------------------------------------------------------------------------


def _e(name: str) -> str:  # type: ignore[no-redef]  # noqa: F811
    """Return emoji glyph if the terminal supports it, else ASCII fallback."""
    pair = _EMOJI.get(name)
    if pair is None:
        return ""
    return pair[0] if _USE_EMOJI else pair[1]


def _b(name: str) -> str:  # type: ignore[no-redef]  # noqa: F811
    """Return box-drawing glyph if the terminal supports it, else ASCII."""
    pair = _BOX.get(name)
    if pair is None:
        return ""
    return pair[0] if _USE_BOXDRAW else pair[1]


def _summarize_transparency_result(result: Dict[str, Any]) -> Dict[str, Any]:
    rekor_result = result.get("rekor_bundle")
    witness_result = result.get("witnessed_checkpoint")
    checkpoint = (
        rekor_result.get("checkpoint") if isinstance(rekor_result, dict) else None
    )
    verified_witnesses = (
        witness_result.get("verified_witnesses")
        if isinstance(witness_result, dict)
        else None
    )
    errors = result.get("errors")
    error_count = len(errors) if isinstance(errors, list) else 0
    if error_count == 0 and result.get("error"):
        error_count = 1
    return {
        "valid": bool(result.get("valid")),
        "artifact_hash_match": bool(result.get("artifact_hash_match")),
        "body_hash_match": bool(result.get("body_hash_match")),
        "inclusion_proof_verified": bool(
            isinstance(rekor_result, dict)
            and rekor_result.get("inclusion_proof_verified")
        ),
        "checkpoint_signature_verified": bool(
            isinstance(checkpoint, dict) and checkpoint.get("log_signature_verified")
        ),
        "witnessed_checkpoint_provided": bool(
            isinstance(witness_result, dict) and witness_result.get("provided")
        ),
        "witnessed_checkpoint_verified": bool(
            isinstance(witness_result, dict) and witness_result.get("valid")
        ),
        "verified_witness_count": (
            len(verified_witnesses) if isinstance(verified_witnesses, list) else 0
        ),
        "error_count": error_count,
    }


def _verification_target_label(result: Dict[str, Any]) -> str:
    """Return a short subject label for verification summaries."""

    if result.get("receipt_type") == "commitment_receipt":
        name = _strip_terminal_escapes(str(result.get("subject_name", "unknown")))[:60]
        kind = _strip_terminal_escapes(str(result.get("subject_kind", "")))[:30]
        return f"subject={name}" if not kind else f"subject={name} ({kind})"
    return f"commit={_strip_terminal_escapes(str(result.get('commit_sha', 'unknown')))[:12]}"


def _emit_receipt_outputs(
    receipts: Sequence[Dict[str, Any]],
    args: argparse.Namespace,
    *,
    default_stdout: bool = False,
) -> Optional[Dict[str, Any]]:
    """Handle pretty/detail output, file writes, signing, and stdout emission."""

    if args.sign and not args.output:
        print(
            f"{_e('error')} --sign needs --output too (bundles are saved as sidecar files).",
            file=sys.stderr,
        )
        print(
            f"   {_e('hint')} Try: aiir --sign --output .receipts",
            file=sys.stderr,
        )
        return None
    if args.sign and not _sigstore_available():
        print(
            f"{_e('error')} Signing needs the 'sigstore' package.",
            file=sys.stderr,
        )
        print(
            f"   {_e('hint')} Install it: pip install sigstore",
            file=sys.stderr,
        )
        return None

    explicit_stdout = args.json_stdout or args.jsonl or default_stdout
    signed_count = 0
    output_paths: List[str] = []
    signed_display = "YES (sigstore)" if args.sign else "none"

    if args.detail:
        for receipt in receipts:
            print(
                format_receipt_detail(receipt, signed=signed_display), file=sys.stderr
            )
    elif args.pretty:
        for receipt in receipts:
            print(
                format_receipt_pretty(receipt, signed=signed_display), file=sys.stderr
            )

    if args.output or args.sign:
        for receipt in receipts:
            try:
                path = write_receipt(receipt, output_dir=args.output, jsonl=args.jsonl)
            except ValueError as e:
                print(f"{_e('error')} {e}", file=sys.stderr)
                print(
                    f"   {_e('hint')} Use a folder inside your project, e.g. --output .receipts",
                    file=sys.stderr,
                )
                return None
            output_paths.append(path)
            if args.sign and path and not path.startswith("stdout:"):
                try:
                    bundle_path = sign_receipt_file(path)
                    signed_count += 1
                    if not args.quiet:
                        print(
                            f"  {_e('signed')} Signed: {bundle_path}", file=sys.stderr
                        )
                except Exception as e:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    err_msg = _strip_terminal_escapes(str(e))[:200]
                    print(f"{_e('error')} Signing failed: {err_msg}", file=sys.stderr)
                    print(
                        f"   {_e('hint')} The unsigned receipt was removed. Check your internet connection and try again.",
                        file=sys.stderr,
                    )
                    return None

    if explicit_stdout:
        if args.jsonl:
            for receipt in receipts:
                try:
                    write_receipt(receipt, output_dir=None, jsonl=True)
                except ValueError as e:
                    print(f"{_e('error')} {e}", file=sys.stderr)
                    return None
        else:
            payload: Any = receipts[0] if len(receipts) == 1 else list(receipts)
            print(json.dumps(payload, indent=2, ensure_ascii=False), flush=True)

    return {
        "explicit_stdout": explicit_stdout,
        "signed_count": signed_count,
        "output_paths": output_paths,
    }


# ---------------------------------------------------------------------------
# CLI main
# ---------------------------------------------------------------------------


# Subclass ArgumentParser to show did-you-mean suggestions when
# the user passes an unrecognised flag (e.g. --prettty → did you mean --pretty?).
class _FriendlyParser(argparse.ArgumentParser):
    """ArgumentParser that suggests close matches for unrecognised flags."""

    def error(self, message: str) -> NoReturn:  # noqa: D401 (argparse override)
        if "unrecognized arguments:" in message:
            bad = message.split("unrecognized arguments:")[-1].strip().split()
            # Sanitise user tokens before echoing to stderr
            safe_bad = " ".join(_strip_terminal_escapes(t) for t in bad)
            known = [a.option_strings for a in self._actions if a.option_strings]
            flat = [f for opts in known for f in opts]
            hints = []
            for token in bad:
                close = difflib.get_close_matches(token, flat, n=1, cutoff=0.6)
                if close:
                    hints.append(f"  {_e('hint')} Did you mean {close[0]} ?")
            if hints:
                self.exit(
                    2,
                    f"{_e('error')} Unknown flag: {safe_bad}\n"
                    + "\n".join(hints)
                    + "\n",
                )
            # Always use friendly format, no fallthrough
            self.exit(2, f"{_e('error')} Unknown flag: {safe_bad}\n")
        # Fall through for all other argparse errors (including
        # mutually-exclusive group violations) — keep default behaviour.
        super().error(message)


_DOCTOR_MANAGED_HOOK_START = "# >>> AIIR managed post-commit hook >>>"
_DOCTOR_MANAGED_HOOK_END = "# <<< AIIR managed post-commit hook <<<"
_DEFAULT_MANAGED_HOOK_ARGS = ["--pretty", "--skip-receipt-only-commits"]


def _receipt_only_touches_ledger(
    receipt: Dict[str, Any], ledger_dir: Optional[str]
) -> bool:
    commit = receipt.get("commit")
    if not isinstance(commit, dict):
        return False

    raw_files = commit.get("files")
    if isinstance(raw_files, dict):
        changed_files = raw_files.get("files")
    else:
        changed_files = raw_files
    if not isinstance(changed_files, list) or not changed_files:
        return False

    ledger_root = str(PurePosixPath(Path(ledger_dir or _LEDGER_DIR).as_posix())).strip(
        "/"
    )
    if not ledger_root:
        return False

    prefix = ledger_root + "/"
    for changed in changed_files:
        if not isinstance(changed, str):
            return False
        normalized = str(PurePosixPath(changed)).strip("/")
        if normalized != ledger_root and not normalized.startswith(prefix):
            return False
    return True


def _should_skip_receipt_only_commits(
    receipts: Sequence[Dict[str, Any]], ledger_dir: Optional[str]
) -> bool:
    return bool(receipts) and all(
        _receipt_only_touches_ledger(receipt, ledger_dir=ledger_dir)
        for receipt in receipts
    )


def _doctor_resolve_ledger_dir(base_dir: Path, ledger_arg: Optional[str]) -> Path:
    ledger_dir = Path(ledger_arg or _LEDGER_DIR)
    if not ledger_dir.is_absolute():
        ledger_dir = base_dir / ledger_dir
    return ledger_dir


def _get_post_commit_hook_path(repo_root: Path) -> Path:
    hook_path_raw = _run_git(
        ["rev-parse", "--git-path", "hooks/post-commit"],
        cwd=str(repo_root),
    ).strip()
    hook_path = Path(hook_path_raw)
    if not hook_path.is_absolute():
        hook_path = repo_root / hook_path
    return hook_path


def _looks_like_shell_hook(existing: str) -> bool:
    first_line = existing.splitlines()[0] if existing.splitlines() else ""
    if not first_line:
        return True
    if not first_line.startswith("#!"):
        return True
    return any(shell in first_line for shell in ("sh", "bash", "zsh", "dash"))


def _build_managed_hook_block(
    cli_command: str = "aiir",
    hook_args: Optional[Sequence[str]] = None,
) -> str:
    hook_parts = [cli_command, *(hook_args or _DEFAULT_MANAGED_HOOK_ARGS)]
    command = " ".join(shlex.quote(part) for part in hook_parts)
    return "\n".join(
        [
            _DOCTOR_MANAGED_HOOK_START,
            "# Managed by AIIR CLI.",
            f"{command} >/dev/null 2>&1 || {command}",
            _DOCTOR_MANAGED_HOOK_END,
        ]
    )


def _write_post_commit_hook(hook_path: Path, contents: str) -> None:
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(contents, encoding="utf-8")
    try:
        os.chmod(hook_path, hook_path.stat().st_mode | stat.S_IXUSR)
    except OSError:
        pass


def _install_managed_post_commit_hook(
    repo_root: Path,
    allow_append: bool = False,
    allow_replace: bool = False,
) -> Dict[str, str]:
    if allow_append and allow_replace:
        raise ValueError("Choose only one of --hook-append or --hook-replace.")

    hook_path = _get_post_commit_hook_path(repo_root)
    managed_block = _build_managed_hook_block()

    try:
        existing = (
            hook_path.read_text(encoding="utf-8") if hook_path.is_file() else None
        )
    except OSError as e:
        raise RuntimeError(f"Could not read post-commit hook: {e}") from e

    next_content = "#!/bin/sh\n\n" + managed_block + "\n"
    status = "installed"
    detail = "Installed managed AIIR post-commit hook."

    if existing:
        if (
            _DOCTOR_MANAGED_HOOK_START in existing
            and _DOCTOR_MANAGED_HOOK_END in existing
        ):
            next_content = existing.replace(
                existing[
                    existing.index(_DOCTOR_MANAGED_HOOK_START) : existing.index(
                        _DOCTOR_MANAGED_HOOK_END
                    )
                    + len(_DOCTOR_MANAGED_HOOK_END)
                ],
                managed_block,
            )
            status = "updated"
            detail = "Updated existing managed AIIR hook block."
        elif not _looks_like_shell_hook(existing):
            if not allow_replace:
                raise ValueError(
                    "Existing non-shell post-commit hook found. Re-run with --hook-replace to replace it."
                )
            status = "replaced"
            detail = "Replaced existing non-shell post-commit hook."
        else:
            if allow_replace:
                status = "replaced"
                detail = "Replaced existing custom shell post-commit hook."
            elif allow_append:
                next_content = existing.rstrip() + "\n\n" + managed_block + "\n"
                status = "updated"
                detail = (
                    "Appended managed AIIR hook block to existing custom shell hook."
                )
            else:
                raise ValueError(
                    "Existing custom shell post-commit hook found. Re-run with --hook-append to preserve it or --hook-replace to overwrite it."
                )

    _write_post_commit_hook(hook_path, next_content)
    return {
        "action": "install_hook",
        "status": status,
        "hook_path": str(hook_path),
        "managed_hook_state": "managed",
        "detail": detail,
    }


def _remove_managed_post_commit_hook(repo_root: Path) -> Dict[str, str]:
    hook_path = _get_post_commit_hook_path(repo_root)
    if not hook_path.is_file():
        return {
            "action": "remove_hook",
            "status": "absent",
            "hook_path": str(hook_path),
            "managed_hook_state": "missing",
            "detail": "No post-commit hook is installed.",
        }

    try:
        existing = hook_path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"Could not read post-commit hook: {e}") from e

    if (
        _DOCTOR_MANAGED_HOOK_START not in existing
        or _DOCTOR_MANAGED_HOOK_END not in existing
    ):
        return {
            "action": "remove_hook",
            "status": "absent",
            "hook_path": str(hook_path),
            "managed_hook_state": "custom",
            "detail": "No managed AIIR hook block was found.",
        }

    start = existing.index(_DOCTOR_MANAGED_HOOK_START)
    end = existing.index(_DOCTOR_MANAGED_HOOK_END) + len(_DOCTOR_MANAGED_HOOK_END)
    stripped = (existing[:start] + existing[end:]).strip()

    if not stripped or stripped == "#!/bin/sh":
        try:
            hook_path.unlink()
        except OSError as e:
            raise RuntimeError(f"Could not remove post-commit hook: {e}") from e
    else:
        _write_post_commit_hook(hook_path, stripped + "\n")

    return {
        "action": "remove_hook",
        "status": "removed",
        "hook_path": str(hook_path),
        "managed_hook_state": "missing",
        "detail": "Removed managed AIIR hook block.",
    }


def _doctor_detect_hook_state(repo_root: Path) -> str:
    try:
        hook_path = _get_post_commit_hook_path(repo_root)
    except (FileNotFoundError, OSError, RuntimeError):
        return "unknown"
    if not hook_path.is_file():
        return "missing"

    try:
        hook_contents = hook_path.read_text(encoding="utf-8")
    except OSError:
        return "unknown"

    if (
        _DOCTOR_MANAGED_HOOK_START in hook_contents
        and _DOCTOR_MANAGED_HOOK_END in hook_contents
    ):
        return "managed"
    return "custom"


def _doctor_detect_head_receipt_status(
    head_sha: Optional[str], ledger_dir: Path
) -> str:
    if not head_sha:
        return "unknown"

    index_path = ledger_dir / "index.json"
    if index_path.is_file():
        try:
            index = _load_index(index_path)
        except (OSError, ValueError, json.JSONDecodeError):
            index = None
        if isinstance(index, dict):
            commits = index.get("commits", {})
            if isinstance(commits, dict) and head_sha in commits:
                return "present"

    ledger_path = ledger_dir / "receipts.jsonl"
    if not ledger_path.is_file():
        return "missing"

    try:
        with ledger_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    receipt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                commit = receipt.get("commit", {})
                if isinstance(commit, dict) and commit.get("sha") == head_sha:
                    return "present"
    except OSError:
        return "unknown"

    return "missing"


def _collect_doctor_state(ledger_arg: Optional[str] = None) -> Dict[str, Any]:
    base_dir = Path.cwd()
    state: Dict[str, Any] = {
        "cli_available": True,
        "cli_version": CLI_VERSION,
        "git_available": False,
        "branch": None,
        "head_sha": None,
        "aiir_dir_exists": False,
        "ledger_exists": False,
        "index_exists": False,
        "policy_exists": False,
        "managed_hook_state": "unknown",
        "head_receipt_status": "unknown",
        "provenance_queue_exists": False,
    }

    repo_root: Optional[Path] = None
    try:
        _run_git(["--version"], cwd=str(base_dir))
    except FileNotFoundError:
        state["git_available"] = False
    except (OSError, RuntimeError):
        state["git_available"] = True
    else:
        state["git_available"] = True

    if state["git_available"]:
        try:
            repo_root = Path(get_repo_root())
        except (RuntimeError, FileNotFoundError, OSError):
            repo_root = None

    if repo_root is not None:
        base_dir = repo_root
        try:
            branch = _run_git(
                ["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo_root)
            ).strip()
        except (FileNotFoundError, OSError, RuntimeError):
            branch = None
        if branch:
            state["branch"] = branch

        try:
            head_sha = _run_git(["rev-parse", "HEAD"], cwd=str(repo_root)).strip()
        except (FileNotFoundError, OSError, RuntimeError):
            head_sha = None
        if head_sha:
            state["head_sha"] = head_sha

        state["managed_hook_state"] = _doctor_detect_hook_state(repo_root)

    ledger_dir = _doctor_resolve_ledger_dir(base_dir, ledger_arg)
    state["aiir_dir_exists"] = ledger_dir.is_dir()
    state["ledger_exists"] = (ledger_dir / "receipts.jsonl").is_file()
    state["index_exists"] = (ledger_dir / "index.json").is_file()
    state["policy_exists"] = (ledger_dir / "policy.json").is_file()
    state["provenance_queue_exists"] = (
        ledger_dir / "editor_provenance.jsonl"
    ).is_file()
    state["head_receipt_status"] = _doctor_detect_head_receipt_status(
        state["head_sha"],
        ledger_dir,
    )
    return state


def _format_doctor_report(
    state: Dict[str, Any], ledger_arg: Optional[str] = None
) -> str:
    ledger_label = ledger_arg or _LEDGER_DIR

    def _status(flag: bool) -> str:
        return "present" if flag else "missing"

    branch = state["branch"] or "unavailable"
    head_sha = state["head_sha"] or "unavailable"
    return "\n".join(
        [
            f"{_e('ok')} AIIR doctor",
            f"   CLI version: {state['cli_version']}",
            f"   Git: {'available' if state['git_available'] else 'missing'}",
            f"   Branch: {branch}",
            f"   HEAD: {head_sha}",
            f"   {ledger_label}/: {_status(state['aiir_dir_exists'])}",
            f"   Ledger: {_status(state['ledger_exists'])}",
            f"   Index: {_status(state['index_exists'])}",
            f"   Policy: {_status(state['policy_exists'])}",
            f"   Managed hook: {state['managed_hook_state']}",
            f"   HEAD receipt: {state['head_receipt_status']}",
            f"   Provenance queue: {_status(state['provenance_queue_exists'])}",
        ]
    )


def _ensure_ledger_initialized(
    ledger_dir: str, namespace: Optional[str] = None
) -> List[str]:
    aiir_path = Path(ledger_dir)
    aiir_path.mkdir(parents=True, exist_ok=True)

    created: List[str] = []

    gitignore = aiir_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# AIIR receipts — commit this directory for an audit trail.\n"
            "# Uncomment lines below to exclude specific files:\n"
            "editor_provenance.jsonl\n"
            "# *.sigstore\n"
            "# config.json\n",
            encoding="utf-8",
        )
        created.append(".gitignore")

    receipts_file = aiir_path / "receipts.jsonl"
    if not receipts_file.exists():
        receipts_file.write_text("", encoding="utf-8")
        created.append("receipts.jsonl")

    index_file = aiir_path / "index.json"
    if not index_file.exists():
        index_file.write_text(
            json.dumps({"receipt_count": 0, "receipts": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        created.append("index.json")

    config_file = aiir_path / "config.json"
    if not config_file.exists():
        import uuid as _uuid

        config_data: Dict[str, Any] = {"instance_id": str(_uuid.uuid4())}
        if namespace:
            config_data["namespace"] = namespace
        config_file.write_text(
            json.dumps(config_data, indent=2) + "\n",
            encoding="utf-8",
        )
        created.append("config.json")

    return created


def _expand_shorthand_command(argv: Sequence[str]) -> List[str]:
    if not argv:
        return list(argv)
    command = argv[0].strip().lower()
    mapping = {
        "quickstart": ["--quickstart"],
        "setup": ["--quickstart"],
        "status": ["--status"],
        "ci": ["--ci"],
        "install-hook": ["--install-hook"],
    }
    if command not in mapping:
        return list(argv)
    return [*mapping[command], *argv[1:]]


def _summarize_ledger_receipts(ledger_path: Path) -> Dict[str, int]:
    summary = {
        "receipt_count": 0,
        "ai_receipt_count": 0,
        "signed_receipt_count": 0,
        "unsigned_receipt_count": 0,
    }
    if not ledger_path.is_file():
        return summary
    try:
        index = _load_index(ledger_path.parent / "index.json")
    except OSError:
        index = {}
    if int(index.get("receipt_count", 0) or 0) > 0:
        summary["receipt_count"] = int(index.get("receipt_count", 0) or 0)
        summary["ai_receipt_count"] = int(index.get("ai_commit_count", 0) or 0)
        summary["signed_receipt_count"] = int(index.get("signed_receipt_count", 0) or 0)
        summary["unsigned_receipt_count"] = int(
            index.get("unsigned_receipt_count", 0) or 0
        )
        return summary
    try:
        receipts = _load_receipts_from_ledger(str(ledger_path))
    except (OSError, ValueError, FileNotFoundError):
        return summary
    summary["receipt_count"] = len(receipts)
    summary["ai_receipt_count"] = sum(
        1
        for receipt in receipts
        if isinstance(receipt, dict)
        and isinstance(receipt.get("ai_attestation"), dict)
        and receipt["ai_attestation"].get("is_ai_authored") is True
    )
    summary["signed_receipt_count"] = sum(
        1
        for receipt in receipts
        if isinstance(receipt, dict) and _receipt_is_signed(receipt)
    )
    summary["unsigned_receipt_count"] = (
        summary["receipt_count"] - summary["signed_receipt_count"]
    )
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    raw_argv = _expand_shorthand_command(
        list(argv) if argv is not None else sys.argv[1:]
    )
    parser = _FriendlyParser(
        prog="aiir",
        description="AIIR - AI Integrity Receipts. Generate cryptographic receipts for git commits.",
        epilog=(
            "examples:\n"
            "  aiir                        Receipt HEAD → .aiir/receipts.jsonl\n"
            "  aiir --pretty               Same, plus human-readable summary\n"
            "  aiir --doctor               Report local repo readiness and AIIR state\n"
            "  aiir --doctor --json        Same, as stable JSON\n"
            "  aiir quickstart             One-shot setup (hook + ledger + verify)\n"
            "  aiir setup                  Alias for quickstart\n"
            "  aiir status                 Concise local receipt status\n"
            "  aiir ci                     CI gate: verify receipt ledger\n"
            "  aiir --install-hook         Install managed local auto-receipting\n"
            "  aiir --remove-hook          Remove the managed AIIR hook block\n"
            "  aiir --init                 Initialize .aiir/ for a new project\n"
            "  aiir --detail               Full receipt details (all fields)\n"
            "  aiir -r origin/main..HEAD   Receipt every commit in a range\n"
            "  aiir --ai-only              Only AI-authored commits\n"
            "  aiir --json                 Print JSON to stdout (for piping)\n"
            "  aiir -o .receipts           Individual receipt files in a dir\n"
            "  aiir --verify receipt.json   Verify a receipt's integrity\n"
            "  aiir --sign -o .receipts    Sign receipt with Sigstore\n"
            "  aiir --check --policy strict CI gate: fail if policy violated\n"
            "  aiir --stats                Ledger statistics dashboard\n"
            "  aiir --explain              Explain the last verification\n"
            "\n"
            "default: receipts are appended to .aiir/receipts.jsonl and\n"
            "auto-indexed in .aiir/index.json (one entry per commit SHA,\n"
            "duplicates skipped).  Add .aiir/ to your repo for an audit trail.\n"
            "\n"
            "exit codes:\n"
            "  0  Success (receipts generated, or verification passed)\n"
            "  1  Error (verification failed, git error, bad input)\n"
            "\n"
            "https://github.com/invariant-systems-ai/aiir  |  "
            "https://invariantsystems.io"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Report local repository and AIIR ledger state without changing anything",
    )
    parser.add_argument(
        "--quickstart",
        action="store_true",
        help="One-shot setup: install hook, initialize ledger, seed a receipt, and verify",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print concise local AIIR status (repo, receipts, HEAD verification, AI usage)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Single-step CI verification for .aiir/receipts.jsonl",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        dest="install_hook",
        help="Install or update the managed AIIR post-commit hook",
    )
    parser.add_argument(
        "--remove-hook",
        action="store_true",
        dest="remove_hook",
        help="Remove the managed AIIR post-commit hook block if present",
    )
    parser.add_argument(
        "--hook-append",
        action="store_true",
        help="Append the managed AIIR hook block to an existing custom shell hook",
    )
    parser.add_argument(
        "--hook-replace",
        action="store_true",
        help="Replace an existing post-commit hook when installing the managed AIIR hook",
    )
    parser.add_argument(
        "--commit",
        "-c",
        default=None,
        help="Specific commit SHA to receipt (default: HEAD)",
    )
    parser.add_argument(
        "--range",
        "-r",
        default=None,
        dest="range_spec",
        help="Commit range to receipt (e.g., 'origin/main..HEAD')",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Only generate receipts for AI-authored commits",
    )
    parser.add_argument(
        "--skip-receipt-only-commits",
        action="store_true",
        help=(
            "Skip receipt generation when the target commit only changes files "
            "inside the AIIR ledger directory; intended for post-commit hooks"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output directory for individual receipt JSON files (for CI)",
    )
    parser.add_argument(
        "--ledger",
        "-l",
        nargs="?",
        const=_LEDGER_DIR,
        default=None,
        metavar="DIR",
        help=(
            "Append receipts to a JSONL ledger directory (default: .aiir/). "
            "The directory will contain receipts.jsonl and index.json. "
            "Duplicates are auto-skipped. "
            "This is the default when no output flags are given."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_stdout",
        help="Print raw JSON to stdout instead of writing to ledger (for piping)",
    )
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Output as JSON Lines to stdout (one receipt per line)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print human-readable summary (combines with ledger by default)",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Print detailed human-readable receipt (all fields, combines with any mode)",
    )
    parser.add_argument(
        "--github-action",
        action="store_true",
        help="Run in GitHub Actions mode (set outputs + step summary)",
    )
    parser.add_argument(
        "--gitlab-ci",
        action="store_true",
        help=(
            "Run in GitLab CI mode (post MR comments, write dotenv outputs, "
            "set generator to 'aiir.gitlab')"
        ),
    )
    parser.add_argument(
        "--gl-sast-report",
        nargs="?",
        const="gl-sast-report.json",
        default=None,
        metavar="FILE",
        help=(
            "Write a GitLab SAST report (gl-sast-report.json) for Security "
            "Dashboard integration. AI-authored commits appear as "
            "informational findings."
        ),
    )
    # --quiet and --verbose are mutually exclusive.
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress non-essential output",
    )
    verbosity_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging (git commands, timing, signal evaluation)",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"aiir {CLI_VERSION}",
    )
    parser.add_argument(
        "--verify",
        default=None,
        metavar="FILE",
        help="Verify a receipt JSON file's content-addressed integrity",
    )
    parser.add_argument(
        "--artifact",
        default=None,
        metavar="FILE",
        help=(
            "Verify offline transparency material for an artifact. "
            "Use with --rekor-bundle, --trust-root, and optionally "
            "--witnessed-checkpoint."
        ),
    )
    parser.add_argument(
        "--rekor-bundle",
        default=None,
        metavar="FILE",
        help=(
            "Path to a Sigstore bundle or aiir.rekor.bundle.v1 document "
            "for --artifact verification."
        ),
    )
    parser.add_argument(
        "--trust-root",
        default=None,
        metavar="FILE",
        help=(
            "Path to an aiir.trust.v1 trust root for offline checkpoint and "
            "witness verification."
        ),
    )
    parser.add_argument(
        "--witnessed-checkpoint",
        default=None,
        metavar="FILE",
        help=(
            "Path to a raw signed checkpoint note carrying witness "
            "cosignatures for --artifact verification."
        ),
    )
    parser.add_argument(
        "--require-witnesses",
        default=None,
        metavar="POLICY",
        help=(
            "Witness quorum for --artifact verification. Accepts N-of-M or a "
            "named policy from the trust root, such as 'release'."
        ),
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Show human-readable explanation of verification result (use with --verify)",
    )
    parser.add_argument(
        "--in-toto",
        action="store_true",
        dest="in_toto",
        help=(
            "Wrap receipts in an in-toto Statement v1 envelope "
            "(https://in-toto.io/Statement/v1). Makes AIIR receipts native "
            "to the supply-chain attestation ecosystem (SLSA, Sigstore "
            "policy-controller, Kyverno, OPA/Gatekeeper, Tekton Chains)."
        ),
    )
    parser.add_argument(
        "--sign",
        action="store_true",
        help="Sign receipts using Sigstore keyless signing (requires pip install sigstore)",
    )
    parser.add_argument(
        "--verify-signature",
        action="store_true",
        help=(
            "Also verify Sigstore signature when using --verify "
            "(checks the .sigstore bundle, Rekor linkage, and signature trust chain)"
        ),
    )
    parser.add_argument(
        "--signer-identity",
        default=None,
        metavar="IDENTITY",
        help="Expected signer identity for --verify-signature (email or OIDC subject)",
    )
    parser.add_argument(
        "--signer-issuer",
        default=None,
        metavar="ISSUER",
        help="Expected OIDC issuer URL for --verify-signature",
    )
    parser.add_argument(
        "--verify-release",
        action="store_true",
        dest="verify_release",
        help=(
            "Verify a release by evaluating receipts against policy. "
            "Produces a Verification Summary Attestation (VSA). "
            "Use with --range, --receipts, --policy, --emit-vsa."
        ),
    )
    parser.add_argument(
        "--receipts",
        default=None,
        metavar="PATH",
        help=(
            "Path to receipts ledger (JSONL) or directory of receipt JSONs. "
            "Default: .aiir/receipts.jsonl. Used with --verify-release."
        ),
    )
    parser.add_argument(
        "--emit-vsa",
        nargs="?",
        const="aiir-vsa.intoto.jsonl",
        default=None,
        metavar="FILE",
        dest="emit_vsa",
        help=(
            "Write the Verification Summary Attestation as an in-toto Statement "
            "to a file. Default filename: aiir-vsa.intoto.jsonl. Used with --verify-release."
        ),
    )
    parser.add_argument(
        "--subject",
        default=None,
        metavar="SUBJECT",
        help=(
            "Subject identifier for the VSA (e.g., 'oci://registry/app@sha256:...'). "
            "Default: auto-detected from git remote + HEAD. Used with --verify-release."
        ),
    )
    parser.add_argument(
        "--redact-files",
        action="store_true",
        help="Omit individual file paths from receipts (privacy; mitigates I-05 file enumeration)",
    )
    parser.add_argument(
        "--redact-emails",
        action="store_true",
        help="Replace author and committer emails with deterministic pseudonyms in receipts",
    )
    parser.add_argument(
        "--namespace",
        default=None,
        metavar="NS",
        help=(
            "Tag receipts with an organization namespace (e.g., 'acme-corp'). "
            "Stored in extensions.namespace — not part of the content hash, "
            "so adding or changing a namespace does not invalidate receipts."
        ),
    )
    parser.add_argument(
        "--agent-tool",
        default=None,
        metavar="TOOL",
        help=(
            "Declare the AI tool identity (e.g., 'copilot', 'cursor', 'claude-code'). "
            "Stored in extensions.agent_attestation — not part of the content hash."
        ),
    )
    parser.add_argument(
        "--agent-model",
        default=None,
        metavar="MODEL",
        help=(
            "Declare the AI model class (e.g., 'gpt-4o', 'claude-sonnet-4-20250514'). "
            "Stored in extensions.agent_attestation."
        ),
    )
    parser.add_argument(
        "--agent-context",
        default=None,
        metavar="CTX",
        help=(
            "Declare the run context (e.g., 'ide', 'cli', 'ci', 'mcp'). "
            "Stored in extensions.agent_attestation."
        ),
    )
    parser.add_argument(
        "--tool-context",
        default=None,
        metavar="JSON",
        help=(
            "Attach companion IDE or workflow context as JSON object/array. "
            "Stored in extensions.tool_context and excluded from the content hash."
        ),
    )
    parser.add_argument(
        "--editor-provenance",
        nargs="?",
        const=f"{_LEDGER_DIR}/editor_provenance.jsonl",
        default=None,
        metavar="FILE",
        help=(
            "Consume one queued editor provenance record from FILE and attach it "
            "to extensions.editor_provenance when generating a receipt. "
            f"Default: {_LEDGER_DIR}/editor_provenance.jsonl."
        ),
    )
    parser.add_argument(
        "--export",
        nargs="?",
        const="aiir-export.json",
        default=None,
        metavar="FILE",
        help=(
            "Export ledger as a portable JSON bundle (for backup or import). "
            "Path must be relative to the project root."
        ),
    )
    parser.add_argument(
        "--badge",
        action="store_true",
        help="Print a shields.io badge Markdown snippet from ledger stats",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print a summary dashboard of ledger statistics",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run policy checks against ledger stats (for CI gates)",
    )
    parser.add_argument(
        "--max-ai-percent",
        type=float,
        default=None,
        metavar="N",
        help="Policy gate: fail if AI-authored percentage exceeds N (use with --check)",
    )
    parser.add_argument(
        "--policy",
        default=None,
        metavar="PRESET",
        help=(
            "Apply a policy preset or load .aiir/policy.json. "
            "Presets: strict, balanced, permissive. "
            "Use with --check for aggregate policy evaluation."
        ),
    )
    parser.add_argument(
        "--policy-init",
        default=None,
        metavar="PRESET",
        help=(
            "Initialize .aiir/policy.json from a preset (strict, balanced, permissive). "
            "Creates the file and exits."
        ),
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help=(
            "Initialize a .aiir/ directory for the current project. "
            "Creates receipts.jsonl, index.json, config.json, and .gitignore. "
            "Optionally pass --policy to set a policy preset."
        ),
    )
    parser.add_argument(
        "--commitment-artifact",
        action="append",
        default=None,
        metavar="PATH",
        help=(
            "Add a file or directory to a generic commitment receipt. "
            "Repeatable. Use with --commitment-name and --commitment-summary."
        ),
    )
    parser.add_argument(
        "--commitment-digest",
        action="append",
        default=None,
        metavar="LABEL=sha256:HEX",
        help=(
            "Add a precomputed digest to a generic commitment receipt. "
            "Repeatable. Use with --commitment-name and --commitment-summary."
        ),
    )
    parser.add_argument(
        "--commitment-name",
        default=None,
        metavar="NAME",
        help="Subject name for a generic commitment receipt.",
    )
    parser.add_argument(
        "--commitment-kind",
        default=None,
        metavar="KIND",
        help=(
            "Subject kind for a generic commitment receipt "
            "(default: artifact_commitment)."
        ),
    )
    parser.add_argument(
        "--commitment-summary",
        default=None,
        metavar="TEXT",
        help="Human-readable summary for a generic commitment receipt.",
    )
    parser.add_argument(
        "--review",
        nargs="?",
        const="HEAD",
        default=None,
        metavar="COMMIT",
        help=(
            "Generate a review receipt for a commit (default: HEAD). "
            "Attests that a human reviewed the commit. "
            "Use --review-outcome to set approved/rejected/commented."
        ),
    )
    parser.add_argument(
        "--review-outcome",
        default="approved",
        metavar="OUTCOME",
        help=(
            "Review outcome: approved, rejected, or commented (default: approved). "
            "Used with --review."
        ),
    )
    parser.add_argument(
        "--review-comment",
        default=None,
        metavar="TEXT",
        help="Optional review comment (used with --review).",
    )
    parser.add_argument(
        "--trailer",
        action="store_true",
        help=(
            "Print AIIR commit trailer lines to stdout after receipt generation. "
            "Suitable for appending to git commit messages via "
            "'git interpret-trailers'."
        ),
    )

    args = parser.parse_args(raw_argv)

    # Configure logging based on --verbose flag or AIIR_LOG_LEVEL env.
    log_level = os.environ.get("AIIR_LOG_LEVEL", "DEBUG" if args.verbose else "WARNING")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.WARNING),
        format="%(name)s %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # --- Policy init mode (no git repo needed) ---
    if args.policy_init:
        try:
            policy, policy_path = init_policy(
                preset=args.policy_init,
                ledger_dir=args.ledger if args.ledger else _LEDGER_DIR,
            )
            print(
                f"{_e('ok')} Policy initialized: {policy_path}"
                f" (preset: {args.policy_init})",
                file=sys.stderr,
            )
            print(
                f"   {_e('hint')} Enforcement: {policy.get('enforcement', 'warn')}"
                f" | Signing: {'required' if policy.get('require_signing') else 'optional'}"
                f" | Max AI: {policy.get('max_ai_percent', 100)}%",
                file=sys.stderr,
            )
            return 0
        except ValueError as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

    # --- Quickstart mode (install hook + initialize + demo receipt + verify) ---
    if args.quickstart:
        if args.jsonl:
            message = "--quickstart supports --json, not --jsonl."
            if args.json_stdout:
                print(
                    json.dumps(
                        {"mode": "quickstart", "ok": False, "error": message},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"{_e('error')} {message}", file=sys.stderr)
            return 1
        try:
            repo_root = Path(get_repo_root())
        except (RuntimeError, FileNotFoundError, OSError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        hook_warning: Optional[str] = None
        try:
            _install_managed_post_commit_hook(repo_root, allow_append=True)
        except ValueError:
            hook_warning = (
                "Existing custom post-commit hook detected; kept as-is. "
                "Run `aiir --install-hook --hook-append` when ready."
            )
        except RuntimeError as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        ledger_dir = args.ledger if args.ledger else _LEDGER_DIR
        _ensure_ledger_initialized(ledger_dir, namespace=args.namespace)

        try:
            receipt = generate_receipt("HEAD", cwd=str(repo_root), generator="aiir.cli")
            if receipt is None:
                print(
                    f"{_e('error')} Could not generate demo receipt for HEAD.",
                    file=sys.stderr,
                )
                return 1
            append_to_ledger([receipt], ledger_dir=ledger_dir)
        except (RuntimeError, ValueError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        verify_path = str(Path(ledger_dir) / "receipts.jsonl")
        verify_result = verify_receipt_ledger_file(verify_path)
        if not verify_result.get("valid"):
            print(
                f"{_e('error')} Quickstart verification failed.",
                file=sys.stderr,
            )
            return 1

        verified_count = int(
            verify_result.get(
                "valid_receipts",
                verify_result.get("count", 0),
            )
        )
        receipt_word = "receipt" if verified_count == 1 else "receipts"
        quickstart_result: Dict[str, Any] = {
            "mode": "quickstart",
            "active": True,
            "ledger_path": verify_path,
            "verified_receipts": verified_count,
            "hook_installed": hook_warning is None,
            "hook_warning": hook_warning,
        }
        if args.json_stdout:
            print(json.dumps(quickstart_result, indent=2, ensure_ascii=False))
        else:
            print(
                f"{_e('ok')} AIIR active - receipts will be recorded on every commit",
                file=sys.stderr,
            )
            if hook_warning:
                print(f"⚠ {hook_warning}", file=sys.stderr)
            else:
                print(f"{_e('ok')} Managed post-commit hook installed", file=sys.stderr)
            print(
                f"{_e('ok')} Verified ({verified_count} {receipt_word})",
                file=sys.stderr,
            )
            print(f"Ledger: {verify_path}", file=sys.stderr)
            print("Run `git commit` to record your next receipt.", file=sys.stderr)
        return 0

    # --- Status mode (single-shot health summary) ---
    if args.status:
        if args.jsonl:
            message = "--status supports --json, not --jsonl."
            if args.json_stdout:
                print(
                    json.dumps(
                        {"mode": "status", "ok": False, "error": message},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"{_e('error')} {message}", file=sys.stderr)
            return 1
        state = _collect_doctor_state(args.ledger)
        repo_label = "clean" if state.get("git_available") else "unavailable"
        ledger_dir = args.ledger if args.ledger else _LEDGER_DIR
        status_ledger_path = Path(ledger_dir) / "receipts.jsonl"
        ledger_summary = _summarize_ledger_receipts(status_ledger_path)
        receipts_count = ledger_summary["receipt_count"]
        ai_receipts_count = ledger_summary["ai_receipt_count"]
        signed_receipts_count = ledger_summary["signed_receipt_count"]
        unsigned_receipts_count = ledger_summary["unsigned_receipt_count"]

        last_commit_status = (
            "verified" if state.get("head_receipt_status") == "present" else "missing"
        )
        status_result: Dict[str, Any] = {
            "mode": "status",
            "repo": repo_label,
            "receipts": receipts_count,
            "last_commit": last_commit_status,
            "ai_usage_commits": ai_receipts_count,
            "signed_receipts": signed_receipts_count,
            "unsigned_receipts": unsigned_receipts_count,
            "ledger_path": str(status_ledger_path),
            "managed_hook_state": state.get("managed_hook_state", "unknown"),
        }
        if args.json_stdout:
            print(json.dumps(status_result, indent=2, ensure_ascii=False))
        else:
            print(f"Repo: {repo_label}", file=sys.stderr)
            print(f"Receipts: {receipts_count}", file=sys.stderr)
            print(f"Last commit: {last_commit_status}", file=sys.stderr)
            print(f"AI usage: detected ({ai_receipts_count} commits)", file=sys.stderr)
            print(
                f"Signing: {signed_receipts_count} signed, {unsigned_receipts_count} unsigned",
                file=sys.stderr,
            )
        return 0

    # --- CI mode (single-command verification gate) ---
    if args.ci:
        if args.jsonl:
            message = "--ci supports --json, not --jsonl."
            if args.json_stdout:
                print(
                    json.dumps(
                        {"mode": "ci", "ok": False, "error": message},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"{_e('error')} {message}", file=sys.stderr)
            return 1
        ledger_dir = args.ledger if args.ledger else _LEDGER_DIR
        ci_receipts_path = Path(ledger_dir) / "receipts.jsonl"
        if not ci_receipts_path.is_file():
            message = f"Missing receipt ledger: {ci_receipts_path}"
            if args.json_stdout:
                print(
                    json.dumps(
                        {"mode": "ci", "valid": False, "error": message},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"{_e('error')} {message}", file=sys.stderr)
            return 1
        result = verify_receipt_ledger_file(str(ci_receipts_path))
        if not result.get("valid"):
            message = "Receipt verification failed."
            if args.json_stdout:
                print(
                    json.dumps(
                        {"mode": "ci", "valid": False, "error": message},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                print(f"{_e('error')} {message}", file=sys.stderr)
            return 1
        ci_summary = _summarize_ledger_receipts(ci_receipts_path)
        total = ci_summary["receipt_count"]
        ai_count = ci_summary["ai_receipt_count"]
        signed_count = ci_summary["signed_receipt_count"]
        unsigned_count = ci_summary["unsigned_receipt_count"]
        ai_percent = (ai_count / total * 100.0) if total else 0.0
        if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
            set_github_output("AIIR_RECEIPT_COUNT", str(total))
            set_github_output("AIIR_AI_COMMIT_COUNT", str(ai_count))
            set_github_output("AIIR_AI_PERCENT", f"{ai_percent:.1f}")
            set_github_output("AIIR_SIGNED_RECEIPT_COUNT", str(signed_count))
            set_github_output("AIIR_UNSIGNED_RECEIPT_COUNT", str(unsigned_count))
            set_github_summary(
                "\n".join(
                    [
                        f"## {_e('check')} AIIR CI Verify",
                        "",
                        f"- Receipts: **{total}**",
                        f"- AI-authored commits: **{ai_count}** ({ai_percent:.1f}%)",
                        f"- Signed receipts: **{signed_count}**",
                        f"- Unsigned receipts: **{unsigned_count}**",
                        f"- Ledger: `{ci_receipts_path}`",
                    ]
                )
            )
        if os.environ.get("GITLAB_CI"):
            set_gitlab_ci_output("AIIR_RECEIPT_COUNT", str(total))
            set_gitlab_ci_output("AIIR_AI_COMMIT_COUNT", str(ai_count))
            set_gitlab_ci_output("AIIR_AI_PERCENT", f"{ai_percent:.1f}")
            set_gitlab_ci_output("AIIR_SIGNED_RECEIPT_COUNT", str(signed_count))
            set_gitlab_ci_output("AIIR_UNSIGNED_RECEIPT_COUNT", str(unsigned_count))
        ci_result: Dict[str, Any] = {
            "mode": "ci",
            "valid": True,
            "ledger_path": str(ci_receipts_path),
            "receipts": total,
            "ai_commits": ai_count,
            "ai_percent": round(ai_percent, 1),
            "signed_receipts": signed_count,
            "unsigned_receipts": unsigned_count,
        }
        if args.json_stdout:
            print(json.dumps(ci_result, indent=2, ensure_ascii=False))
        else:
            print(
                f"{_e('ok')} AIIR CI verify passed ({total} receipt(s)).",
                file=sys.stderr,
            )
        return 0

    # --- Init mode (scaffolds .aiir/ directory) ---
    if args.init:
        ledger_dir = args.ledger if args.ledger else _LEDGER_DIR
        aiir_path = Path(ledger_dir)

        # Guard: don't escape project root.
        # Use relative_to() — NOT startswith() — to prevent the
        # prefix-collision bug: /repo vs /repo_evil both pass startswith.
        # (Same pattern as write_receipt's path traversal guard.)
        try:
            resolved = aiir_path.resolve()
            cwd_resolved = Path.cwd().resolve()
            try:
                resolved.relative_to(cwd_resolved)
            except ValueError:
                print(
                    f"{_e('error')} Ledger dir must be within the project root.",
                    file=sys.stderr,
                )
                return 1
        except OSError:
            pass  # resolve may fail on some platforms; continue

        created = _ensure_ledger_initialized(ledger_dir, namespace=args.namespace)

        # Optionally init policy too
        if args.policy:
            try:
                _p, _pp = init_policy(
                    preset=args.policy if args.policy in POLICY_PRESETS else "balanced",
                    ledger_dir=ledger_dir,
                )
                created.append("policy.json")
            except ValueError:
                pass

        if created:
            print(
                f"{_e('ok')} Initialized {ledger_dir}/ with: {', '.join(created)}",
                file=sys.stderr,
            )
        else:
            print(
                f"{_e('ok')} {ledger_dir}/ already initialized (no changes).",
                file=sys.stderr,
            )
        print(
            f"   {_e('hint')} Add {ledger_dir}/ to your repo: git add {ledger_dir}/",
            file=sys.stderr,
        )
        return 0

    # --- Doctor mode (local state inspection, no mutations) ---
    if args.doctor:
        if args.jsonl:
            print(
                f"{_e('error')} --doctor supports --json, not --jsonl.",
                file=sys.stderr,
            )
            return 1
        doctor_state = _collect_doctor_state(args.ledger)
        if args.json_stdout:
            print(json.dumps(doctor_state, indent=2, ensure_ascii=False))
        else:
            print(_format_doctor_report(doctor_state, args.ledger), file=sys.stderr)
        return 0

    # --- Managed hook lifecycle (local-only, repo mutation) ---
    if args.install_hook or args.remove_hook:
        if args.install_hook and args.remove_hook:
            print(
                f"{_e('error')} Choose only one of --install-hook or --remove-hook.",
                file=sys.stderr,
            )
            return 1
        if args.remove_hook and (args.hook_append or args.hook_replace):
            print(
                f"{_e('error')} --hook-append and --hook-replace only apply to --install-hook.",
                file=sys.stderr,
            )
            return 1
        try:
            repo_root = Path(get_repo_root())
        except (RuntimeError, FileNotFoundError, OSError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1
        try:
            if args.install_hook:
                hook_result = _install_managed_post_commit_hook(
                    repo_root,
                    allow_append=args.hook_append,
                    allow_replace=args.hook_replace,
                )
            else:
                hook_result = _remove_managed_post_commit_hook(repo_root)
        except (RuntimeError, ValueError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        if args.jsonl:
            print(
                f"{_e('error')} Hook lifecycle commands support --json, not --jsonl.",
                file=sys.stderr,
            )
            return 1
        if args.json_stdout:
            print(json.dumps(hook_result, indent=2, ensure_ascii=False))
        else:
            print(f"{_e('ok')} {hook_result['detail']}", file=sys.stderr)
            print(f"   Status: {hook_result['status']}", file=sys.stderr)
            print(f"   Hook: {hook_result['hook_path']}", file=sys.stderr)
        return 0

    # --- Generic commitment receipt mode ---
    commitment_requested = any(
        value
        for value in (
            args.commitment_artifact,
            args.commitment_digest,
            args.commitment_name,
            args.commitment_kind,
            args.commitment_summary,
        )
    )
    if commitment_requested:
        missing = []
        if not args.commitment_name:
            missing.append("--commitment-name")
        if not args.commitment_summary:
            missing.append("--commitment-summary")
        if not args.commitment_artifact and not args.commitment_digest:
            missing.append("--commitment-artifact or --commitment-digest")
        if missing:
            print(
                f"{_e('error')} Commitment mode is incomplete. Missing: {', '.join(missing)}",
                file=sys.stderr,
            )
            return 1
        if args.commit or args.range_spec or args.review is not None:
            print(
                f"{_e('error')} Commitment mode cannot be combined with commit receipt generation or review mode.",
                file=sys.stderr,
            )
            return 1

        commitment_generator = "aiir.cli"
        if args.github_action:
            commitment_generator = "aiir.github"
        elif args.gitlab_ci:
            commitment_generator = "aiir.gitlab"

        commitment_artifacts = []
        try:
            for artifact_path in args.commitment_artifact or []:
                commitment_artifacts.append(
                    build_commitment_path_artifact(artifact_path)
                )
            for digest_spec in args.commitment_digest or []:
                commitment_artifacts.append(parse_commitment_digest_spec(digest_spec))
            receipt = build_commitment_receipt(
                subject_name=args.commitment_name,
                summary=args.commitment_summary,
                artifacts=commitment_artifacts,
                subject_kind=args.commitment_kind or "artifact_commitment",
                cwd=os.getcwd(),
                namespace=getattr(args, "namespace", None),
                generator=commitment_generator,
            )
        except ValueError as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        commitment_receipts = [receipt]
        if getattr(args, "in_toto", False):
            commitment_receipts = [
                wrap_in_toto_statement(r) for r in commitment_receipts
            ]

        output_result = _emit_receipt_outputs(
            commitment_receipts,
            args,
            default_stdout=not args.output and not args.sign,
        )
        if output_result is None:
            return 1

        if not args.quiet and not args.jsonl:
            summary = [f"{_e('ok')} 1 commitment receipt generated"]
            summary.append(
                f"{_e('check')} {len(commitment_artifacts)} artifact(s) declared"
            )
            if output_result["signed_count"]:
                summary.append(f"{_e('signed')} {output_result['signed_count']} signed")
            print("\n" + " | ".join(summary), file=sys.stderr)
            if output_result["output_paths"]:
                print(
                    f"   {_e('hint')} Saved to {output_result['output_paths'][0]}",
                    file=sys.stderr,
                )
        return 0

    # --- Review receipt mode ---
    if args.review is not None:
        try:
            cwd_review = get_repo_root()
        except (RuntimeError, FileNotFoundError, OSError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        # Resolve the ref to a full SHA — the review receipt schema requires
        # a hex SHA (^[0-9a-f]{40}$ or ^[0-9a-f]{64}$), not a symbolic ref
        # like "HEAD" or a short SHA like "abc1234".
        reviewed_ref = args.review
        try:
            reviewed_sha = _run_git(["rev-parse", reviewed_ref], cwd=cwd_review).strip()
            if not reviewed_sha:
                raise RuntimeError(f"Could not resolve ref: {reviewed_ref}")
        except RuntimeError as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        # Get reviewer identity from git config
        try:
            reviewer_name = _run_git(["config", "user.name"], cwd=cwd_review).strip()
            reviewer_email = _run_git(["config", "user.email"], cwd=cwd_review).strip()
        except RuntimeError:
            reviewer_name = os.environ.get("GIT_AUTHOR_NAME", "unknown")
            reviewer_email = os.environ.get("GIT_AUTHOR_EMAIL", "unknown")

        if not reviewer_name or not reviewer_email:
            print(
                f"{_e('error')} Cannot determine reviewer identity. "
                "Set git config user.name and user.email.",
                file=sys.stderr,
            )
            return 1

        # Build agent attestation from CLI flags (if any).
        _review_attestation = None
        if (
            getattr(args, "agent_tool", None)
            or getattr(args, "agent_model", None)
            or getattr(args, "agent_context", None)
        ):
            _review_attestation = {}
            if args.agent_tool:
                _review_attestation["tool_id"] = args.agent_tool
            if args.agent_model:
                _review_attestation["model_class"] = args.agent_model
            if args.agent_context:
                _review_attestation["run_context"] = args.agent_context
            _review_attestation["confidence"] = "declared"

        # Determine generator ID based on integration mode
        _review_generator = "aiir.cli"
        if getattr(args, "github_action", False):
            _review_generator = "aiir.github"
        elif getattr(args, "gitlab_ci", False):
            _review_generator = "aiir.gitlab"

        try:
            review_receipt = build_review_receipt(
                reviewed_commit=reviewed_sha,
                reviewer_name=reviewer_name,
                reviewer_email=reviewer_email,
                review_outcome=args.review_outcome,
                comment=args.review_comment,
                cwd=cwd_review,
                agent_attestation=_review_attestation,
                generator=_review_generator,
            )
        except (ValueError, RuntimeError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        # Output the review receipt
        if args.json_stdout:
            print(json.dumps(review_receipt, indent=2, ensure_ascii=False), flush=True)
        elif args.jsonl:
            print(
                json.dumps(review_receipt, separators=(",", ":"), ensure_ascii=False),
                flush=True,
            )
        else:
            # Append to ledger
            ledger_dir = args.ledger if args.ledger is not None else _LEDGER_DIR
            try:
                append_to_ledger(
                    [review_receipt],
                    ledger_dir=ledger_dir,
                )
            except ValueError as e:
                print(f"{_e('error')} {e}", file=sys.stderr)
                return 1

        if not args.quiet:
            rid = review_receipt.get("receipt_id", "")[:24]
            sha_short = reviewed_sha[:12]
            print(
                f"\n{_e('ok')} Review receipt: {rid}…",
                file=sys.stderr,
            )
            print(
                f"   Reviewed: {sha_short}  Outcome: {args.review_outcome}",
                file=sys.stderr,
            )
            if args.review_comment:
                print(
                    f"   Comment: {_strip_terminal_escapes(args.review_comment)[:80]}",
                    file=sys.stderr,
                )

        if args.json_stdout or args.jsonl:
            pass  # already printed
        else:
            print(json.dumps(review_receipt, indent=2, ensure_ascii=False))
        return 0

    # --- Verify mode (no git repo needed) ---
    if args.artifact:
        if args.verify:
            print(
                f"{_e('error')} Choose only one of --verify or --artifact.",
                file=sys.stderr,
            )
            return 1
        if not args.rekor_bundle:
            print(
                f"{_e('error')} Artifact verification requires --rekor-bundle.",
                file=sys.stderr,
            )
            return 1
        if not args.trust_root:
            print(
                f"{_e('error')} Artifact verification requires --trust-root.",
                file=sys.stderr,
            )
            return 1

        result = verify_transparency_material(
            args.artifact,
            args.rekor_bundle,
            args.trust_root,
            witnessed_checkpoint_path=args.witnessed_checkpoint,
            require_witnesses=args.require_witnesses,
        )
        if result.get("valid"):
            print(
                f"{_e('ok')} Artifact transparency verified -- offline proofs intact.",
                file=sys.stderr,
            )
            print(json.dumps(_summarize_transparency_result(result), indent=2))
            return 0

        print(
            f"{_e('error')} Artifact transparency verification failed.",
            file=sys.stderr,
        )
        print(json.dumps(_summarize_transparency_result(result), indent=2))
        return 1

    if args.verify:
        verify_target = Path(args.verify)
        verify_is_ledger = verify_target.suffix.lower() == ".jsonl"
        result = (
            verify_receipt_ledger_file(args.verify)
            if verify_is_ledger
            else verify_receipt_file(args.verify)
        )
        if result.get("valid"):
            if verify_is_ledger:
                count = result.get("count", 0)
                valid_receipts = result.get("valid_receipts", count)
                print(
                    f"{_e('ok')} All good! {valid_receipts}/{count} ledger receipts verified -- integrity intact.",
                    file=sys.stderr,
                )
                print(json.dumps(result, indent=2))
                return 0

            # Inference receipt results have receipt_type set
            rtype = result.get("receipt_type", "")
            if rtype == "inference_receipt" or (
                isinstance(result.get("valid_hashes"), int)
            ):
                # Single or chain inference receipt
                if "total" in result:
                    total = result["total"]
                    print(
                        f"{_e('ok')} Inference chain verified: {result['valid_hashes']}/{total}"
                        f" hashes valid, {result.get('valid_links', 0)} chain links intact.",
                        file=sys.stderr,
                    )
                else:
                    g = result.get("granularity", "unknown")
                    tc = result.get("token_count", "?")
                    print(
                        f"{_e('ok')} Inference receipt verified -- "
                        f"granularity={g}, tokens={tc}, integrity intact.",
                        file=sys.stderr,
                    )
                print(json.dumps(result, indent=2))
                return 0

            if rtype == "commitment_receipt" and "receipts" not in result:
                print(
                    f"{_e('ok')} Commitment receipt verified -- integrity intact.",
                    file=sys.stderr,
                )
                print(
                    f"   {result['receipt_id'][:24]}... {_verification_target_label(result)} {_e('check')}",
                    file=sys.stderr,
                )
                if args.verify_signature:
                    sig_result = verify_receipt_signature(
                        args.verify,
                        expected_identity=args.signer_identity,
                        expected_issuer=args.signer_issuer,
                    )
                    result["signature"] = sig_result
                    if sig_result.get("valid"):
                        policy = sig_result.get("policy", "any")
                        print(
                            f"{_e('ok')} Signature verified (policy={policy})",
                            file=sys.stderr,
                        )
                    else:
                        sig_err = sig_result.get("error", "Unknown signature error")
                        print(
                            f"{_e('error')} Signature FAILED: {sig_err}",
                            file=sys.stderr,
                        )
                        print(json.dumps(result, indent=2))
                        return 1
                if getattr(args, "explain", False):
                    print("", file=sys.stderr)
                    print(explain_verification(result), file=sys.stderr)
                print(json.dumps(result, indent=2))
                return 0

            if rtype == "research_evidence_receipt":
                if "total" in result:
                    print(
                        f"{_e('ok')} Research evidence receipt set verified: "
                        f"{result.get('valid_receipts', 0)}/{result['total']} receipts intact.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"{_e('ok')} Research evidence receipt verified -- "
                        f"claim_id={result.get('claim_id', 'unknown')}, "
                        f"disclosure_tier={result.get('disclosure_tier', 'unknown')}, integrity intact.",
                        file=sys.stderr,
                    )
                print(json.dumps(result, indent=2))
                return 0

            count = result.get("count", 1)
            print(
                f"{_e('ok')} All good! {count} receipt{'s' if count != 1 else ''} verified -- integrity intact.",
                file=sys.stderr,
            )
            if "receipts" in result:
                for r in result["receipts"]:
                    print(
                        f"   {r['receipt_id'][:24]}... {_verification_target_label(r)} {_e('check')}",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"   {result['receipt_id'][:24]}... {_verification_target_label(result)} {_e('check')}",
                    file=sys.stderr,
                )

            # Sigstore signature verification (optional)
            if args.verify_signature:
                sig_result = verify_receipt_signature(
                    args.verify,
                    expected_identity=args.signer_identity,
                    expected_issuer=args.signer_issuer,
                )
                result["signature"] = sig_result
                if sig_result.get("valid"):
                    policy = sig_result.get("policy", "any")
                    bundle_summary = sig_result.get("bundle", {})
                    print(
                        f"{_e('ok')} Signature verified (policy={policy})",
                        file=sys.stderr,
                    )
                    if isinstance(bundle_summary, dict):
                        bundle_entries = bundle_summary.get("entries") or []
                        if bundle_entries:
                            first_entry = bundle_entries[0]
                            details = []
                            if first_entry.get("kind"):
                                details.append(str(first_entry["kind"]))
                            if first_entry.get("log_index"):
                                details.append(f"logIndex={first_entry['log_index']}")
                            if first_entry.get("integrated_time_rfc3339"):
                                details.append(
                                    f"integrated={first_entry['integrated_time_rfc3339']}"
                                )
                            if details:
                                print(
                                    f"   Rekor: {', '.join(details)}",
                                    file=sys.stderr,
                                )
                        if bundle_summary.get("certificate_sha256"):
                            print(
                                "   Certificate: "
                                f"{bundle_summary['certificate_sha256'][:31]}...",
                                file=sys.stderr,
                            )
                    if args.signer_identity:
                        print(
                            f"   Expected signer: {_strip_terminal_escapes(args.signer_identity)[:120]}",
                            file=sys.stderr,
                        )
                    if args.signer_issuer:
                        print(
                            f"   Expected issuer: {_strip_terminal_escapes(args.signer_issuer)[:120]}",
                            file=sys.stderr,
                        )
                else:
                    sig_err = sig_result.get("error", "Unknown signature error")
                    print(
                        f"{_e('error')} Signature FAILED: {sig_err}",
                        file=sys.stderr,
                    )
                    bundle_errors = sig_result.get("errors") or []
                    for bundle_error in bundle_errors[:5]:
                        if bundle_error == sig_err:
                            continue
                        print(f"   * {bundle_error}", file=sys.stderr)
                    if getattr(args, "explain", False):
                        print("", file=sys.stderr)
                        print(explain_verification(result), file=sys.stderr)
                    print(json.dumps(result, indent=2))
                    return 1

            if getattr(args, "explain", False):
                print("", file=sys.stderr)
                print(explain_verification(result), file=sys.stderr)
            print(json.dumps(result, indent=2))
            return 0
        else:
            if verify_is_ledger:
                count = result.get("count", 0)
                valid_receipts = result.get("valid_receipts", 0)
                print(
                    f"{_e('error')} Ledger verification failed: {valid_receipts}/{count} receipts valid.",
                    file=sys.stderr,
                )
                for err in result.get("errors", [])[:5]:
                    print(f"   * {err}", file=sys.stderr)
                print(json.dumps(result, indent=2))
                return 1

            # Inference receipt failure path
            rtype = result.get("receipt_type", "")
            if rtype == "inference_receipt" or isinstance(
                result.get("valid_hashes"), int
            ):
                errs = result.get("errors", [])
                if "total" in result:
                    total = result["total"]
                    print(
                        f"{_e('error')} Inference chain verification failed: "
                        f"{result.get('valid_hashes', 0)}/{total} hashes valid.",
                        file=sys.stderr,
                    )
                    for err in errs[:5]:
                        print(f"   * {err}", file=sys.stderr)
                else:
                    err_msg = errs[0] if errs else "hash mismatch"
                    print(
                        f"{_e('error')} Inference receipt verification failed: {err_msg}",
                        file=sys.stderr,
                    )
            elif rtype == "research_evidence_receipt":
                errs = result.get("errors", [])
                if "total" in result:
                    print(
                        f"{_e('error')} Research evidence receipt set verification failed: "
                        f"{result.get('valid_receipts', 0)}/{result.get('total', 0)} receipts valid.",
                        file=sys.stderr,
                    )
                    for err in errs[:5]:
                        print(f"   * {err}", file=sys.stderr)
                else:
                    err_msg = errs[0] if errs else "integrity mismatch"
                    print(
                        f"{_e('error')} Research evidence receipt verification failed: {err_msg}",
                        file=sys.stderr,
                    )
            # When an array of receipts has failures, show
            # which specific receipts failed instead of a generic message.
            elif "receipts" in result:
                failed = [r for r in result["receipts"] if not r.get("valid")]
                total = result.get("count", len(result["receipts"]))
                print(
                    f"{_e('error')} Verification failed: {len(failed)} of {total}"
                    f" receipt{'s' if total != 1 else ''} invalid.",
                    file=sys.stderr,
                )
                for r in failed[:5]:
                    rid = str(r.get("receipt_id", "unknown"))[:24]
                    errs = r.get("errors", [])
                    err_msg = errs[0] if errs else "content hash mismatch"
                    print(f"   * {rid}... -- {err_msg}", file=sys.stderr)
            else:
                error = result.get(
                    "error", "Content hash mismatch -- receipt may be tampered"
                )
                print(f"{_e('error')} Verification failed: {error}", file=sys.stderr)
            # Context-aware verify tips — "receipt was changed" is
            # misleading for file-not-found and parse errors.  Show a tip that
            # matches the actual failure category.
            error_str = str(result.get("error", ""))
            if "File not found" in error_str:
                print(
                    f"   {_e('hint')} Check the file path and try again.",
                    file=sys.stderr,
                )
            elif "Invalid JSON" in error_str or "not a dict" in error_str:
                print(
                    f"   {_e('hint')} The file doesn't look like an aiir receipt."
                    " Receipts are JSON objects (or arrays of objects).",
                    file=sys.stderr,
                )
            elif "symlink" in error_str:
                print(
                    f"   {_e('hint')} Point --verify at the actual file, not a symlink.",
                    file=sys.stderr,
                )
            elif "too large" in error_str:
                print(
                    f"   {_e('hint')} The file exceeds the size limit."
                    " Is this the right file?",
                    file=sys.stderr,
                )
            else:
                print(
                    f"   {_e('hint')} This means the receipt was changed after it was created,"
                    " or it wasn't generated by aiir.",
                    file=sys.stderr,
                )
            if getattr(args, "explain", False):
                print("", file=sys.stderr)
                print(explain_verification(result), file=sys.stderr)
            print(json.dumps(result, indent=2))
            return 1

    # --- Verify-release mode ---
    if getattr(args, "verify_release", False):
        release_receipts_path = args.receipts or ".aiir/receipts.jsonl"
        # Determine policy
        vr_policy_preset = None
        vr_policy_path = None
        if args.policy:
            from aiir._policy import POLICY_PRESETS as _PP

            if args.policy in _PP:
                vr_policy_preset = args.policy
            else:
                vr_policy_path = args.policy

        # Build policy overrides from CLI flags
        vr_overrides = {}
        if args.max_ai_percent is not None:
            vr_overrides["max_ai_percent"] = args.max_ai_percent

        try:
            vr_result = verify_release(
                commit_range=args.range_spec,
                receipts_path=release_receipts_path,
                policy_path=vr_policy_path,
                policy_preset=vr_policy_preset,
                subject_name=getattr(args, "subject", None),
                emit_intoto=bool(getattr(args, "emit_vsa", None)),
                policy_overrides=vr_overrides if vr_overrides else None,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

        verdict = vr_result.get("verificationResult", "UNKNOWN")
        reason = vr_result.get("reason", "")

        # Print human report to stderr
        report = format_release_report(vr_result)
        print(report, file=sys.stderr)

        # Write in-toto VSA file if requested
        if getattr(args, "emit_vsa", None) and "intoto_statement" in vr_result:
            vsa_path = args.emit_vsa
            from pathlib import Path as _VsaPath

            # Validate path: must resolve within cwd (no symlink escape).
            # Use relative_to() — NOT startswith() — to prevent the
            # prefix-collision bug: /repo vs /repo_evil.
            _vsa_resolved = _VsaPath(vsa_path).resolve()
            try:
                _vsa_resolved.relative_to(_VsaPath.cwd().resolve())
            except ValueError:
                print(
                    f"{_e('error')} VSA path must be relative and within the project.",
                    file=sys.stderr,
                )
                return 1

            out = _VsaPath(vsa_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(vr_result["intoto_statement"], indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            print(
                f"{_e('ok')} VSA written: {vsa_path}",
                file=sys.stderr,
            )

        # Print JSON result to stdout
        if getattr(args, "emit_vsa", None) and "intoto_statement" in vr_result:
            print(json.dumps(vr_result["intoto_statement"], indent=2))
        else:
            print(json.dumps(vr_result, indent=2))

        if verdict == "PASSED":
            print(f"\n{_e('ok')} Release verification PASSED", file=sys.stderr)
            return 0
        else:
            print(
                f"\n{_e('error')} Release verification FAILED: {reason}",
                file=sys.stderr,
            )
            return 1

    # --- Export mode (no git repo needed) ---
    if args.export is not None:
        # Guard: fail early if no ledger exists (matches --badge / --stats).
        try:
            _idx = _load_index(_ledger_paths(args.ledger)[2])
        except OSError:  # pragma: no cover — filesystem error
            _idx = {}
        if _idx.get("receipt_count", 0) == 0:
            print(
                f"{_e('error')} No ledger found — run 'aiir' first to generate receipts.",
                file=sys.stderr,
            )
            return 1
        try:
            bundle = export_ledger(ledger_dir=args.ledger)
        except Exception as e:
            print(f"{_e('error')} Export failed: {e}", file=sys.stderr)
            return 1
        export_path = args.export
        # Validate export path — reject traversal via resolve().
        # Use relative_to() — NOT startswith() — to prevent the
        # prefix-collision bug: /repo vs /repo_evil.
        _export_resolved = Path(export_path).resolve()
        try:
            _export_resolved.relative_to(Path.cwd().resolve())
        except ValueError:
            print(
                f"{_e('error')} Export path must be relative and within the project.",
                file=sys.stderr,
            )
            return 1

        out = Path(export_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        n = len(bundle.get("receipts", []))
        iid = bundle.get("instance_id", "none")[:8]
        print(
            f"{_e('ok')} Exported {n} receipt{'s' if n != 1 else ''} → {export_path}  (instance: {iid}…)",
            file=sys.stderr,
        )
        return 0

    # --- Badge mode (no git repo needed) ---
    if args.badge:
        try:
            idx = _load_index(_ledger_paths(args.ledger)[2])
        except OSError:  # pragma: no cover — filesystem error
            idx = {}
        if idx.get("receipt_count", 0) == 0:
            print(
                f"{_e('error')} No ledger found — run 'aiir' first to generate receipts.",
                file=sys.stderr,
            )
            return 1
        cfg = {}
        try:
            cfg = _load_config(args.ledger)
        except OSError:  # pragma: no cover — filesystem error
            pass
        badge = format_badge(idx, namespace=cfg.get("namespace"))
        print(badge["markdown"])
        print(file=sys.stderr)
        print(
            f"   {_e('hint')} Paste into your README.md for an AI transparency badge.",
            file=sys.stderr,
        )
        print(f"   URL: {badge['url']}", file=sys.stderr)
        return 0

    # --- Stats mode (no git repo needed) ---
    if args.stats:
        try:
            idx = _load_index(_ledger_paths(args.ledger)[2])
        except OSError:  # pragma: no cover — filesystem error
            idx = {}
        if idx.get("receipt_count", 0) == 0:
            print(
                f"{_e('error')} No ledger found — run 'aiir' first to generate receipts.",
                file=sys.stderr,
            )
            return 1
        cfg = {}
        try:
            cfg = _load_config(args.ledger)
        except OSError:  # pragma: no cover — filesystem error
            pass
        print(format_stats(idx, config=cfg), file=sys.stderr)
        return 0

    # --- Check / policy gate mode (no git repo needed) ---
    if args.check or args.max_ai_percent is not None or args.policy:
        try:
            idx = _load_index(_ledger_paths(args.ledger)[2])
        except OSError:  # pragma: no cover — filesystem error
            idx = {}

        # If --policy is set, use the policy engine
        if args.policy:
            try:
                policy = load_policy(
                    ledger_dir=args.ledger if args.ledger else _LEDGER_DIR,
                    preset=args.policy if args.policy in POLICY_PRESETS else None,
                )
            except ValueError as e:
                print(f"{_e('error')} {e}", file=sys.stderr)
                return 1

            # Override max_ai_percent from CLI if given
            if args.max_ai_percent is not None:
                policy["max_ai_percent"] = args.max_ai_percent

            passed, message, violations = evaluate_ledger_policy(idx, policy)
            if violations:
                report = format_policy_report(
                    violations,
                    enforcement=policy.get("enforcement", "warn"),
                )
                print(report, file=sys.stderr)
            if passed:
                print(f"{_e('ok')} {message}", file=sys.stderr)
                return 0
            else:
                print(f"{_e('error')} {message}", file=sys.stderr)
                return 1

        # Legacy --check / --max-ai-percent path (no policy file)
        passed, message = check_policy(
            idx,
            max_ai_percent=args.max_ai_percent,
        )
        if passed:
            print(f"{_e('ok')} {message}", file=sys.stderr)
            return 0
        else:
            print(f"{_e('error')} {message}", file=sys.stderr)
            return 1

    # --- Receipt generation mode ---
    try:
        cwd = get_repo_root()
    except RuntimeError:
        print(f"{_e('error')} Not a git repository.", file=sys.stderr)
        print(
            f"   {_e('hint')} cd into your project first, or run 'git init' to start one.",
            file=sys.stderr,
        )
        return 1
    except FileNotFoundError:
        # Git binary not found on PATH
        print(f"{_e('error')} Can't find git!", file=sys.stderr)
        print(
            f"   {_e('hint')} Install it: https://git-scm.com/downloads",
            file=sys.stderr,
        )
        return 1
    except OSError as e:
        # Catch OS-level errors from get_repo_root() such as
        # permission denied on .git/HEAD, network mount dropped, or
        # corrupted working tree.  Without this the OSError produces an
        # unhandled traceback that leaks internal paths.
        print(f"{_e('error')} Something went wrong: {e}", file=sys.stderr)
        print(
            f"   {_e('hint')} Check that you have permission to read this repo.",
            file=sys.stderr,
        )
        return 1

    receipts: List[Dict[str, Any]] = []

    # Determine output mode early — config loading creates .aiir/ so
    # we only load it when the ledger (or explicit --namespace) is active.
    explicit_stdout = args.json_stdout or args.jsonl
    use_ledger = (
        not explicit_stdout
        and not args.output
        and not args.github_action
        and not args.gitlab_ci
    )
    if args.ledger is not None:
        use_ledger = True

    # Load config for instance_id and namespace only when .aiir/ will be
    # used anyway (ledger mode) or the user explicitly set --namespace.
    instance_id: Optional[str] = None
    namespace: Optional[str] = getattr(args, "namespace", None)
    if use_ledger or namespace:
        ledger_cfg_dir = args.ledger if args.ledger is not None else _LEDGER_DIR
        try:
            config = _load_config(ledger_cfg_dir)
        except OSError:  # pragma: no cover — filesystem error
            config = {}
        instance_id = config.get("instance_id")
        namespace = namespace or config.get("namespace")
        # Persist namespace to config if set via CLI flag.
        if getattr(args, "namespace", None) and args.namespace != config.get(
            "namespace"
        ):
            config["namespace"] = args.namespace
            try:
                _save_config(_config_path(ledger_cfg_dir), config)
            except OSError:  # pragma: no cover — filesystem error
                pass

    # Build agent attestation from CLI flags (if any).
    agent_attestation = None
    if (
        getattr(args, "agent_tool", None)
        or getattr(args, "agent_model", None)
        or getattr(args, "agent_context", None)
    ):
        agent_attestation = {}
        if args.agent_tool:
            agent_attestation["tool_id"] = args.agent_tool
        if args.agent_model:
            agent_attestation["model_class"] = args.agent_model
        if args.agent_context:
            agent_attestation["run_context"] = args.agent_context
        agent_attestation["confidence"] = "declared"

    # Determine generator ID based on integration mode
    generator = "aiir.cli"
    if args.github_action:
        generator = "aiir.github"
    elif args.gitlab_ci:
        generator = "aiir.gitlab"

    # --- CI environment auto-detection ---
    # When running in GitHub Actions or GitLab CI, the environment tells us
    # whether an AI/bot actor triggered the workflow.  This is stronger than
    # "declared" (self-reported) because the CI platform sets these variables,
    # not the caller.  We only auto-populate if the user did NOT explicitly
    # set --agent-* flags (explicit always wins).
    if agent_attestation is None and (args.github_action or args.gitlab_ci):
        _ci_actor: Optional[str] = None
        _ci_context: Optional[str] = None
        if args.github_action:
            _ci_actor = os.environ.get("GITHUB_ACTOR", "")
            _ci_context = "github-actions"
        elif args.gitlab_ci:  # pragma: no branch — outer guard guarantees one is True
            _ci_actor = os.environ.get(
                "GITLAB_USER_LOGIN", os.environ.get("GITLAB_USER_NAME", "")
            )
            _ci_context = "gitlab-ci"

        # Known AI/bot actor patterns in CI environments
        _ci_ai_actors = {
            "copilot",
            "github-copilot",
            "devin",
            "coderabbit",
            "amazon-q",
            "gitlab-duo",
        }
        _ci_bot_actors = {
            "github-actions[bot]",
            "dependabot[bot]",
            "renovate[bot]",
            "snyk-bot",
            "gitlab-bot",
        }
        if _ci_actor:
            _actor_lower = _ci_actor.lower()
            _is_ai = any(p in _actor_lower for p in _ci_ai_actors)
            _is_bot = any(p in _actor_lower for p in _ci_bot_actors)
            if _is_ai or _is_bot:
                agent_attestation = {
                    "tool_id": _ci_actor,
                    "run_context": _ci_context,
                    "confidence": "environment",
                }

    editor_provenance = None
    if args.editor_provenance:
        if args.range_spec:
            print(
                f"{_e('error')} --editor-provenance only supports single-commit receipt generation.",
                file=sys.stderr,
            )
            return 1
        try:
            current_head_sha = _run_git(["rev-parse", "HEAD"], cwd=cwd).strip() or None
        except RuntimeError:
            current_head_sha = None
        try:
            editor_provenance, _ = consume_editor_provenance(
                args.editor_provenance,
                current_head_sha=current_head_sha,
            )
        except (ValueError, OSError, json.JSONDecodeError) as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

    tool_context = None
    if getattr(args, "tool_context", None):
        try:
            tool_context = json.loads(args.tool_context)
        except json.JSONDecodeError as e:
            print(f"{_e('error')} Invalid --tool-context JSON: {e}", file=sys.stderr)
            return 1
        if not isinstance(tool_context, (dict, list)):
            print(
                f"{_e('error')} --tool-context must decode to a JSON object or array.",
                file=sys.stderr,
            )
            return 1

    try:
        if args.range_spec:
            receipts = generate_receipts_for_range(
                args.range_spec,
                cwd=cwd,
                ai_only=args.ai_only,
                redact_files=args.redact_files,
                redact_emails=args.redact_emails,
                instance_id=instance_id,
                namespace=namespace,
                agent_attestation=agent_attestation,
                tool_context=tool_context,
                generator=generator,
            )
        else:
            commit_ref = args.commit or "HEAD"
            receipt = generate_receipt(
                commit_ref,
                cwd=cwd,
                ai_only=args.ai_only,
                redact_files=args.redact_files,
                redact_emails=args.redact_emails,
                instance_id=instance_id,
                namespace=namespace,
                agent_attestation=agent_attestation,
                editor_provenance=editor_provenance,
                tool_context=tool_context,
                generator=generator,
            )
            if receipt:
                receipts = [receipt]
    except (RuntimeError, ValueError) as e:
        # Detect empty repo (no commits) and show a friendly
        # message instead of leaking the raw git stderr.
        err_str = str(e)
        if "unknown revision" in err_str or "bad default revision" in err_str:
            print(f"{_e('error')} No commits yet.", file=sys.stderr)
            print(
                f"   {_e('hint')} Make your first commit, then run aiir again.",
                file=sys.stderr,
            )
        else:
            print(f"{_e('error')} {e}", file=sys.stderr)
        return 1
    except OSError as e:
        # Catch filesystem errors (e.g., network mount dropped,
        # permission denied on .git, corrupted working tree). Without this,
        # an OSError from subprocess or file I/O produces an unhandled
        # traceback that leaks internal paths.
        print(f"{_e('error')} {e}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        # Git subprocess timeout — surface a clean message instead of
        # an unhandled traceback that leaks internal paths and command strings.
        print(
            f"{_e('error')} Git took too long (>{GIT_TIMEOUT}s). Is the repo very large?",
            file=sys.stderr,
        )
        print(
            f"   {_e('hint')} Try a smaller commit range, or check your network connection.",
            file=sys.stderr,
        )
        return 1

    if not receipts:
        if not args.quiet:
            if args.ai_only:
                print(
                    f"{_e('shrug')} No AI-authored commits found -- --ai-only filtered everything out.",
                    file=sys.stderr,
                )
                print(
                    f"   {_e('hint')} Remove --ai-only to receipt all commits.",
                    file=sys.stderr,
                )
            else:
                print(f"{_e('shrug')} Nothing to receipt here.", file=sys.stderr)
                if args.range_spec:
                    # Sanitize range_spec — user input may
                    # contain terminal escape sequences.
                    print(
                        f"   {_e('hint')} The range may be empty -- check: "
                        "git log --oneline " + _strip_terminal_escapes(args.range_spec),
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"   {_e('hint')} Make sure you have at least one commit: git log --oneline -1",
                        file=sys.stderr,
                    )
        if args.github_action:
            set_github_output("receipt_count", "0")
            set_github_output("ai_commit_count", "0")
            set_github_output("signed_receipt_count", "0")
            set_github_output("unsigned_receipt_count", "0")
        if args.gitlab_ci:
            set_gitlab_ci_output("AIIR_RECEIPT_COUNT", "0")
            set_gitlab_ci_output("AIIR_AI_COMMIT_COUNT", "0")
            set_gitlab_ci_output("AIIR_SIGNED_RECEIPT_COUNT", "0")
            set_gitlab_ci_output("AIIR_UNSIGNED_RECEIPT_COUNT", "0")
        return 0

    ledger_dir = args.ledger if args.ledger is not None else _LEDGER_DIR
    if args.skip_receipt_only_commits and _should_skip_receipt_only_commits(
        receipts, ledger_dir=ledger_dir
    ):
        if not args.quiet:
            print(
                f"{_e('shrug')} Skipping receipt-only AIIR ledger commit.",
                file=sys.stderr,
            )
        return 0

    # ── in-toto envelope wrapping ──────────────────────────────────
    if getattr(args, "in_toto", False):
        receipts = [wrap_in_toto_statement(r) for r in receipts]

    output_result = _emit_receipt_outputs(receipts, args, default_stdout=False)
    if output_result is None:
        return 1

    # Mode C: ledger (default)
    if use_ledger:
        try:
            appended, skipped_count, ledger_path = append_to_ledger(
                receipts,
                ledger_dir=ledger_dir,
            )
        except ValueError as e:
            print(f"{_e('error')} {e}", file=sys.stderr)
            return 1

    # ── Compute stats ──────────────────────────────────────────────────
    ai_count = sum(
        1 for r in receipts if r.get("ai_attestation", {}).get("is_ai_authored")
    )

    # ── Summary (stderr) ───────────────────────────────────────────────
    if not args.quiet and not args.jsonl:
        n = len(receipts)
        parts = [f"{_e('ok')} {n} receipt{'s' if n != 1 else ''} generated"]
        if ai_count:
            parts.append(f"{_e('ai')} {ai_count} AI-authored")
        if output_result["signed_count"]:
            parts.append(f"{_e('signed')} {output_result['signed_count']} signed")
        print("\n" + " | ".join(parts), file=sys.stderr)

        if use_ledger:
            print(
                f"   {_e('hint')} Saved to {ledger_path}"
                + (
                    f" ({skipped_count} duplicate{'s' if skipped_count != 1 else ''} skipped)"
                    if skipped_count
                    else ""
                ),
                file=sys.stderr,
            )

    # Unsigned receipt warning
    if not args.sign and not args.quiet and receipts:
        print(file=sys.stderr)
        print(
            f"{_e('tip')} Tip: these receipts are unsigned. Add --sign for "
            f"Sigstore keyless signing (default in GitHub Actions).",
            file=sys.stderr,
        )

    # No-remote provenance warning
    if not args.quiet and receipts:
        has_no_remote = any(
            r.get("provenance", {}).get("repository") is None for r in receipts
        )
        if has_no_remote:
            print(
                f"   {_e('hint')} No git remote configured. receipt_id will "
                "change once an origin is set (provenance.repository is part "
                "of the content hash).",
                file=sys.stderr,
            )

    # Keep the default happy path quiet; only surface privacy guidance when the
    # caller explicitly asks for verbose stderr output.
    if (
        (not args.redact_files or not args.redact_emails)
        and not args.quiet
        and args.verbose
        and receipts
    ):
        print(
            f"   {_e('hint')} Receipts include author emails and filenames. "
            "Add --redact-files to omit file paths and --redact-emails to pseudonymize identities.",
            file=sys.stderr,
        )

    # GitHub Actions integration
    if args.github_action:
        signed_count = int(output_result["signed_count"])
        set_github_output("receipt_count", str(len(receipts)))
        set_github_output("ai_commit_count", str(ai_count))
        set_github_output("signed_receipt_count", str(signed_count))
        set_github_output("unsigned_receipt_count", str(len(receipts) - signed_count))
        _MAX_OUTPUT_SIZE = 1024 * 1024  # 1 MB
        receipts_payload = _canonical_json(receipts)
        if len(receipts_payload.encode("utf-8", errors="replace")) > _MAX_OUTPUT_SIZE:
            set_github_output("receipts_json", '"OVERFLOW"')
            set_github_output("receipts_overflow", "true")
            print(
                f"WARNING: receipts_json exceeds 1 MB ({len(receipts_payload)} bytes) "
                f"-- output set to OVERFLOW. Use --output to write receipts to files.",
                file=sys.stderr,
            )
        else:
            set_github_output("receipts_json", receipts_payload)

        github_summary = format_github_summary(receipts)
        set_github_summary(github_summary)

        # P0: Create a GitHub Check Run (requires checks: write permission)
        if os.environ.get("GITHUB_TOKEN"):
            try:
                create_check_run(receipts)
                if not args.quiet:
                    print(
                        f"   {_e('ok')} Created aiir/verify check run",
                        file=sys.stderr,
                    )
            except RuntimeError as e:
                # Non-fatal — check run is best-effort
                if not args.quiet:
                    print(
                        f"   {_e('hint')} Could not create check run: "
                        f"{_strip_terminal_escapes(str(e))[:200]}",
                        file=sys.stderr,
                    )

        # P3: Post PR comment (requires pull-requests: write permission)
        if os.environ.get("GITHUB_TOKEN"):
            try:
                post_pr_comment(receipts)
                if not args.quiet:
                    print(
                        f"   {_e('ok')} Posted receipt summary to PR",
                        file=sys.stderr,
                    )
            except RuntimeError as e:
                # Non-fatal — PR comment is best-effort (may not be a PR context)
                logger.debug("PR comment skipped: %s", e)

    # GitLab CI integration
    if args.gitlab_ci:
        set_gitlab_ci_output("AIIR_RECEIPT_COUNT", str(len(receipts)))
        set_gitlab_ci_output("AIIR_AI_COMMIT_COUNT", str(ai_count))
        ai_pct = (ai_count / len(receipts) * 100) if receipts else 0
        set_gitlab_ci_output("AIIR_AI_PERCENT", f"{ai_pct:.1f}")

        # Post MR comment (only in merge_request_event context)
        if os.environ.get("CI_MERGE_REQUEST_IID"):
            try:
                gitlab_summary = format_gitlab_summary(receipts)
                post_mr_comment(gitlab_summary)
                if not args.quiet:
                    print(
                        f"   {_e('ok')} Posted receipt summary to MR !{os.environ.get('CI_MERGE_REQUEST_IID')}",
                        file=sys.stderr,
                    )
            except RuntimeError as e:
                # Non-fatal — MR comment is best-effort
                if not args.quiet:
                    print(
                        f"   {_e('hint')} Could not post MR comment: {_strip_terminal_escapes(str(e))[:200]}",
                        file=sys.stderr,
                    )

    # GitLab SAST report (--gl-sast-report)
    if getattr(args, "gl_sast_report", None):
        from pathlib import Path as _Path

        # Block relative paths that escape the working directory via ".."
        # (absolute paths are an explicit user choice and are allowed).
        _sast_raw = _Path(args.gl_sast_report)
        if not _sast_raw.is_absolute():
            _sast_resolved = _sast_raw.resolve()
            try:
                _sast_resolved.relative_to(_Path.cwd().resolve())
            except ValueError:
                print(
                    f"{_e('error')} SAST report path must be relative and within the project.",
                    file=sys.stderr,
                )
                return 1

        sast_report = format_gl_sast_report(receipts)
        sast_path = _Path(args.gl_sast_report)
        sast_path.parent.mkdir(parents=True, exist_ok=True)
        sast_path.write_text(
            json.dumps(sast_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if not args.quiet:
            vuln_count = len(sast_report.get("vulnerabilities", []))
            print(
                f"   {_e('ok')} SAST report: {vuln_count} AI-authored finding{'s' if vuln_count != 1 else ''} → {args.gl_sast_report}",
                file=sys.stderr,
            )

    # P4: Commit trailer output (--trailer)
    if getattr(args, "trailer", False) and receipts:
        ledger_dir = args.ledger if args.ledger is not None else _LEDGER_DIR
        trailer_text = format_commit_trailer(receipts, ledger_dir=ledger_dir)
        print(trailer_text, end="")

    # Attribution — only when stderr is an interactive terminal.
    if (  # pragma: no cover — interactive-only UI
        not args.quiet
        and not args.github_action
        and not args.gitlab_ci
        and getattr(sys.stderr, "isatty", lambda: False)()
    ):
        print(
            f"\n   {_e('hint')} Like AIIR? ★ https://github.com/invariant-systems-ai/aiir",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
