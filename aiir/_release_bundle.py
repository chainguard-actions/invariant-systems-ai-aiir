# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR internal — portable release evidence bundle.

A release bundle is the canonical handoff artifact for AI-assisted release
evidence.  It packages a release-scoped policy decision (the Verification
Summary Attestation), the receipts that decision was made over, the policy
that was applied, a governance-ready evidence summary, and a human-readable
auditor report into a single self-contained directory that a customer
security team, auditor, or incident reviewer can receive, verify offline,
and archive.

The bundle is the *contract*.  The auditor report is a rendered *view* of the
bundle, never the source of truth — a skeptical reviewer can always drop into
the JSON artifacts and re-verify every claim.

Boundary (repeated in machine- and human-readable form inside every bundle):
  - AIIR records *declared* AI involvement. It does not prove hidden AI use.
  - A missing receipt does not prove a human commit had no AI assistance.
  - A bundle is not a build-provenance, SBOM, or SLSA replacement; it adds the
    AI-involvement layer to that supply-chain evidence stack.

Zero external dependencies — Python standard library + aiir internals only.
"""

from __future__ import annotations

import hashlib
import html
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aiir._core import (
    CLI_VERSION,
    _canonical_json,
    _now_rfc3339,
    _sha256,
    logger,
)
from aiir._evidence import import_evidence_stream, summarize_evidence_stream
from aiir._policy import load_policy
from aiir._verify_release import (
    _load_receipts,
    verify_release,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUNDLE_SCHEMA = "aiir/release_bundle.v1"
BUNDLE_FORMAT_VERSION = 1

# Stable relative paths inside a bundle directory.
_MANIFEST_NAME = "manifest.json"
_MANIFEST_SHA_NAME = "manifest.sha256"
_VERIFY_RELEASE_NAME = "verify-release.json"
_VSA_NAME = "vsa.intoto.json"
_POLICY_NAME = "policy.json"
_EVIDENCE_STREAM_NAME = "evidence-stream.json"
_EVIDENCE_SUMMARY_NAME = "evidence-summary.json"
_REPORT_NAME = "auditor-report.html"
_INSTRUCTIONS_NAME = "verifier-instructions.md"
_README_NAME = "README.md"

# The declared-provenance boundary, stated once and reused everywhere.
_BOUNDARY_LINES = (
    "AIIR records declared AI involvement. It does not prove hidden AI use.",
    "A commit without a receipt is not proof that no AI assistance was used.",
    "A release bundle is not a build-provenance, SBOM, or SLSA replacement; "
    "it adds the AI-involvement layer to that supply-chain evidence stack.",
)


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _json_bytes(obj: Any) -> bytes:
    """Serialize an object as pretty UTF-8 JSON with a trailing newline."""
    return (
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Receipt + signature collection
# ---------------------------------------------------------------------------


def collect_receipt_artifacts(
    receipts_path: str,
    receipts: List[Dict[str, Any]],
) -> List[Tuple[str, bytes, str]]:
    """Collect receipt (and signature) files for inclusion in a bundle.

    Returns a list of ``(relative_path, content_bytes, role)`` tuples.

    For a receipt *directory*, original receipt bytes are copied verbatim so
    that ``content_hash`` and any Sigstore sidecars still verify.  Sidecars
    (``*.json.sigstore`` and ``*.cbor``) are copied alongside under
    ``signatures/`` and ``receipts/`` respectively.

    For a JSONL *ledger*, each receipt is re-serialized deterministically into
    its own file under ``receipts/``.  Re-serialization preserves
    ``content_hash`` verifiability (the hash is computed over receipt fields,
    not file bytes); ledgers carry no per-file signatures.
    """
    artifacts: List[Tuple[str, bytes, str]] = []
    path = Path(receipts_path)

    if path.is_dir():
        for json_path in sorted(path.glob("*.json")):
            if json_path.is_symlink():
                logger.warning("Skipping symlinked receipt: %s", json_path.name)
                continue
            try:
                raw = json_path.read_bytes()
            except OSError:  # pragma: no cover - filesystem error
                logger.warning("Skipping unreadable receipt: %s", json_path.name)
                continue
            artifacts.append((f"receipts/{json_path.name}", raw, "receipt"))

            sig_path = Path(str(json_path) + ".sigstore")
            if sig_path.is_file() and not sig_path.is_symlink():
                artifacts.append(
                    (
                        f"signatures/{sig_path.name}",
                        sig_path.read_bytes(),
                        "sigstore-bundle",
                    )
                )

            cbor_path = json_path.with_suffix(".cbor")
            if cbor_path.is_file() and not cbor_path.is_symlink():
                artifacts.append(
                    (
                        f"receipts/{cbor_path.name}",
                        cbor_path.read_bytes(),
                        "cbor-sidecar",
                    )
                )
        return artifacts

    # JSONL ledger (or any non-directory path): re-serialize each receipt.
    for index, receipt in enumerate(receipts):
        commit = receipt.get("commit", {})
        sha = ""
        if isinstance(commit, dict):
            sha = str(commit.get("sha") or "")
        label = sha[:12] or str(receipt.get("receipt_id") or "receipt")
        # Strip characters that could affect the on-disk name.
        safe_label = "".join(c for c in label if c.isalnum() or c in "-_") or "receipt"
        name = f"receipts/{index:04d}-{safe_label}.json"
        artifacts.append((name, _json_bytes(receipt), "receipt"))
    return artifacts


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def build_bundle_manifest(
    *,
    files: "OrderedDict[str, bytes]",
    roles: Dict[str, str],
    release_name: str,
    commit_range: Optional[str],
    subject: str,
    verification_result: str,
    reason: str,
    policy_digest: str,
    redactions: Dict[str, bool],
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the bundle manifest (``manifest.json`` body).

    Every file in ``files`` except the manifest itself is listed with its
    role and SHA-256 digest.  The manifest is the anchor object: every other
    artifact hangs off it.
    """
    artifacts = [
        {
            "path": relpath,
            "role": roles.get(relpath, "artifact"),
            "sha256": _sha256_bytes(content),
        }
        for relpath, content in files.items()
    ]

    return {
        "schema": BUNDLE_SCHEMA,
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "created_at": created_at or _now_rfc3339(),
        "aiir_version": CLI_VERSION,
        "release": {
            "name": release_name,
            "commit_range": commit_range or "",
            "subject": subject,
        },
        "verification": {
            "result": verification_result,
            "reason": reason,
            "vsa_path": _VSA_NAME,
            "verify_release_result_path": _VERIFY_RELEASE_NAME,
        },
        "policy": {
            "path": _POLICY_NAME,
            "digest": {"sha256": policy_digest},
        },
        "artifacts": artifacts,
        "redactions": {
            "files": bool(redactions.get("files")),
            "emails": bool(redactions.get("emails")),
        },
        "boundary": {
            "declared_ai_provenance_only": True,
            "hidden_ai_detection": False,
            "build_provenance_replacement": False,
        },
    }


# ---------------------------------------------------------------------------
# Auditor HTML report (a rendered view of the bundle)
# ---------------------------------------------------------------------------


def _esc(value: Any) -> str:
    """HTML-escape a value for safe embedding."""
    return html.escape(str(value), quote=True)


def _report_release_section(manifest: Dict[str, Any]) -> str:
    release = manifest.get("release", {})
    rows = [
        ("Release", release.get("name", "")),
        ("Commit range", release.get("commit_range", "") or "(all receipts)"),
        ("Subject", release.get("subject", "")),
        ("Generated", manifest.get("created_at", "")),
        ("AIIR version", manifest.get("aiir_version", "")),
    ]
    cells = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        for label, value in rows
    )
    return (
        "<section><h2>1. What release is this about?</h2>"
        f"<table class='kv'>{cells}</table></section>"
    )


def _report_policy_section(manifest: Dict[str, Any], policy: Dict[str, Any]) -> str:
    digest = manifest.get("policy", {}).get("digest", {}).get("sha256", "")
    preset = policy.get("preset", "(custom)")
    max_ai = policy.get("max_ai_percent")
    rows = [
        ("Policy preset", preset),
        ("Policy digest (sha256)", digest),
        ("Enforcement", policy.get("enforcement", "")),
        ("Signing required", "yes" if policy.get("require_signing") else "no"),
        (
            "Max AI percentage",
            "(unbounded)" if max_ai is None else f"{max_ai}%",
        ),
    ]
    cells = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        for label, value in rows
    )
    return (
        "<section><h2>2. What policy was applied?</h2>"
        f"<table class='kv'>{cells}</table></section>"
    )


def _report_verdict_section(
    verify_result: Dict[str, Any],
) -> str:
    verdict = str(verify_result.get("verificationResult", "UNKNOWN"))
    reason = str(verify_result.get("reason", ""))
    coverage = verify_result.get("coverage", {})
    if not isinstance(coverage, dict):
        coverage = {}
    predicate = verify_result.get("predicate", {})
    evaluation = predicate.get("evaluation", {}) if isinstance(predicate, dict) else {}
    if not isinstance(evaluation, dict):
        evaluation = {}
    violations = verify_result.get("policy_violations", [])
    if not isinstance(violations, list):
        violations = []

    verdict_class = "pass" if verdict == "PASSED" else "fail"
    rows = [
        ("Receipt coverage", f"{coverage.get('coverage_percent', 0)}%"),
        ("Commits in range", coverage.get("commits_total", 0)),
        ("Receipts found", coverage.get("receipts_found", 0)),
        ("Missing receipts", len(coverage.get("receipts_missing", []) or [])),
        ("Invalid receipts", evaluation.get("invalidReceipts", 0)),
        ("Policy violations", evaluation.get("policyViolations", len(violations))),
    ]
    cells = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        for label, value in rows
    )

    viol_html = ""
    if violations:
        items = "".join(
            "<li><code>{sha}</code> {rule}: {msg}</li>".format(
                sha=_esc(str(v.get("commit_sha", ""))[:12]),
                rule=_esc(v.get("rule", "")),
                msg=_esc(v.get("message", "")),
            )
            for v in violations[:50]
            if isinstance(v, dict)
        )
        viol_html = f"<h3>Policy violations</h3><ul class='violations'>{items}</ul>"

    return (
        "<section><h2>3. Did it pass?</h2>"
        f"<p class='verdict {verdict_class}'>{_esc(verdict)}</p>"
        f"<p class='reason'>{_esc(reason)}</p>"
        f"<table class='kv'>{cells}</table>{viol_html}</section>"
    )


def _report_ai_section(summary: Dict[str, Any], redactions: Dict[str, bool]) -> str:
    tiers = summary.get("evidence_tiers", {})
    if not isinstance(tiers, dict):
        tiers = {}
    unsigned = summary.get("unsigned_risk", {})
    if not isinstance(unsigned, dict):
        unsigned = {}
    readiness = summary.get("release_proof_readiness", {})
    if not isinstance(readiness, dict):
        readiness = {}

    rows = [
        ("Total receipts", summary.get("total_receipts", 0)),
        ("AI-involved receipts", summary.get("ai_receipts", 0)),
        ("Signed (release-proof)", tiers.get("signed", 0)),
        ("Provable (unsigned)", tiers.get("provable", 0)),
        ("Heuristic only", tiers.get("heuristic", 0)),
        ("AI receipts without signing", unsigned.get("ai_receipts_without_signing", 0)),
        ("Release-proof readiness", f"{readiness.get('ready_ratio', 0)}%"),
    ]
    cells = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        for label, value in rows
    )

    systems = summary.get("top_ai_systems", [])
    sys_html = ""
    if isinstance(systems, list) and systems:
        items = "".join(
            "<li>{name}: {count}</li>".format(
                name=_esc(s.get("system", "")), count=_esc(s.get("count", 0))
            )
            for s in systems
            if isinstance(s, dict)
        )
        sys_html = f"<h3>Declared AI systems</h3><ul>{items}</ul>"

    hot_html = ""
    if not redactions.get("files"):
        hot_paths = summary.get("hot_path_ai_changes", [])
        if isinstance(hot_paths, list) and hot_paths:
            items = "".join(
                "<li><code>{path}</code> &mdash; {count} AI change(s)</li>".format(
                    path=_esc(p.get("path", "")), count=_esc(p.get("count", 0))
                )
                for p in hot_paths
                if isinstance(p, dict)
            )
            hot_html = f"<h3>Hot paths with AI changes</h3><ul>{items}</ul>"
    else:
        hot_html = "<p class='note'>File paths redacted in this report.</p>"

    return (
        "<section><h2>4. Where was AI declared?</h2>"
        f"<table class='kv'>{cells}</table>{sys_html}{hot_html}</section>"
    )


def _report_boundary_section() -> str:
    items = "".join(f"<li>{_esc(line)}</li>" for line in _BOUNDARY_LINES)
    return (
        "<section class='boundary'><h2>5. What does this <em>not</em> prove?</h2>"
        f"<ul>{items}</ul></section>"
    )


_REPORT_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  margin: 0 auto; max-width: 920px; padding: 2rem 1.5rem; line-height: 1.5; }
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #ccc;
  padding-bottom: 0.25rem; }
h3 { font-size: 1rem; margin-top: 1.25rem; }
table.kv { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
table.kv th, table.kv td { text-align: left; padding: 0.35rem 0.6rem;
  border-bottom: 1px solid #e3e3e3; vertical-align: top; }
table.kv th { width: 14rem; font-weight: 600; }
.verdict { display: inline-block; font-size: 1.4rem; font-weight: 700;
  padding: 0.35rem 1rem; border-radius: 6px; }
.verdict.pass { background: #e6f4ea; color: #137333; }
.verdict.fail { background: #fce8e6; color: #c5221f; }
.reason { color: #555; margin-top: 0.5rem; }
.boundary { background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px;
  padding: 0.5rem 1rem; margin-top: 2rem; }
ul.violations code, code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.85em; }
.note { color: #777; font-style: italic; }
footer { margin-top: 2.5rem; color: #888; font-size: 0.85rem;
  border-top: 1px solid #ccc; padding-top: 0.75rem; }
""".strip()


def render_auditor_report_html(
    *,
    manifest: Dict[str, Any],
    verify_result: Dict[str, Any],
    policy: Dict[str, Any],
    evidence_summary: Dict[str, Any],
    redactions: Dict[str, bool],
) -> str:
    """Render the auditor report as a self-contained, offline HTML document.

    The report is a *view* of the bundle artifacts (manifest, verify-release
    result, policy, evidence summary). It uses only stdlib rendering, embeds
    no external resources, and answers five plain-language questions.
    """
    release = manifest.get("release", {})
    title = f"AIIR Release Evidence — {release.get('name', '')}"
    body = "".join(
        [
            _report_release_section(manifest),
            _report_policy_section(manifest, policy),
            _report_verdict_section(verify_result),
            _report_ai_section(evidence_summary, redactions),
            _report_boundary_section(),
        ]
    )
    footer = (
        "Generated by AIIR "
        f"{_esc(manifest.get('aiir_version', ''))}. This report is a rendered view "
        "of the machine-readable artifacts in this bundle. Verify independently "
        "with the commands in verifier-instructions.md."
    )
    return (
        "<!DOCTYPE html>\n<html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title><style>{_REPORT_CSS}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f"<p>Self-contained, offline-verifiable AI-assisted release evidence.</p>"
        f"{body}<footer>{footer}</footer></body></html>\n"
    )


# ---------------------------------------------------------------------------
# Verifier instructions + README
# ---------------------------------------------------------------------------


def _render_verifier_instructions(manifest: Dict[str, Any]) -> str:
    release = manifest.get("release", {})
    return f"""# Verifier Instructions

This bundle is self-contained and verifiable offline. No account, API key, or
network access is required for content-hash verification.

Release: `{release.get("name", "")}`
Commit range: `{release.get("commit_range", "") or "(all receipts)"}`

## 1. Confirm the manifest is intact

```bash
sha256sum -c {_MANIFEST_SHA_NAME}
```

## 2. Re-hash every artifact against the manifest

```bash
python3 - <<'PY'
import hashlib, json, pathlib
manifest = json.loads(pathlib.Path("{_MANIFEST_NAME}").read_text())
ok = True
for entry in manifest["artifacts"]:
    data = pathlib.Path(entry["path"]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        ok = False
        print("MISMATCH", entry["path"])
print("all artifacts match" if ok else "ARTIFACT MISMATCH")
PY
```

## 3. Verify each receipt's content hash (no trust in AIIR required)

```bash
for f in receipts/*.json; do
  python3 -m aiir --verify "$f" --explain || true
done
```

## 4. Re-run the release policy decision

```bash
python3 -m aiir --verify-release \\
  --receipts receipts/ \\
  --policy {_POLICY_NAME} \\
  --emit-vsa
```

Compare the resulting decision with `{_VERIFY_RELEASE_NAME}` and `{_VSA_NAME}`.

## 5. (Optional) Verify Sigstore signatures

If `signatures/` contains `*.sigstore` bundles, verify them against the matching
receipt with `python -m sigstore verify identity` or
`scripts/check_rekor_bundle.py`.

## Boundary

{chr(10).join("- " + line for line in _BOUNDARY_LINES)}
"""


def _render_bundle_readme(manifest: Dict[str, Any]) -> str:
    release = manifest.get("release", {})
    verification = manifest.get("verification", {})
    return f"""# AIIR Release Evidence Bundle

Self-contained evidence for an AI-assisted software release.

- **Release**: `{release.get("name", "")}`
- **Commit range**: `{release.get("commit_range", "") or "(all receipts)"}`
- **Decision**: **{verification.get("result", "")}** — {verification.get("reason", "")}
- **Generated**: {manifest.get("created_at", "")}
- **AIIR version**: {manifest.get("aiir_version", "")}

## Contents

| File | Role |
|------|------|
| `{_MANIFEST_NAME}` | Anchor manifest — hashes of every artifact |
| `{_MANIFEST_SHA_NAME}` | SHA-256 of the manifest |
| `{_VERIFY_RELEASE_NAME}` | Full release verification result |
| `{_VSA_NAME}` | in-toto Verification Summary Attestation |
| `{_POLICY_NAME}` | Policy that was applied |
| `receipts/` | The receipts the decision was made over |
| `signatures/` | Sigstore sidecars (when present) |
| `{_EVIDENCE_STREAM_NAME}` | Normalized evidence stream |
| `{_EVIDENCE_SUMMARY_NAME}` | Governance-ready evidence summary |
| `{_REPORT_NAME}` | Human-readable auditor report |
| `{_INSTRUCTIONS_NAME}` | Exact commands to re-verify this bundle |

The auditor report is a rendered *view*. The JSON artifacts are the source of
truth — see `{_INSTRUCTIONS_NAME}` to re-verify every claim.

## Boundary

{chr(10).join("- " + line for line in _BOUNDARY_LINES)}
"""


# ---------------------------------------------------------------------------
# Build + write
# ---------------------------------------------------------------------------


def build_release_bundle(
    *,
    commit_range: Optional[str] = None,
    receipts_path: str = ".aiir/receipts.jsonl",
    policy_path: Optional[str] = None,
    policy_preset: Optional[str] = None,
    release_name: Optional[str] = None,
    subject_name: Optional[str] = None,
    emit_report: bool = True,
    redact_files: bool = False,
    redact_emails: bool = False,
    cwd: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a release evidence bundle in memory.

    Runs the release policy decision, collects the receipts it was made over,
    assembles the supporting artifacts, and computes the anchor manifest.
    Does not touch disk except to *read* the source receipts and policy; the
    source ledger is never mutated.

    Returns a dict with:
      - ``files``: ordered map of relative path -> content bytes
      - ``manifest``: the manifest body
      - ``verification_result``: "PASSED" / "FAILED" / ...
      - ``result_code``: 0 if PASSED else 1
    """
    redactions = {"files": bool(redact_files), "emails": bool(redact_emails)}

    # 1) Run the policy decision (also produces the in-toto VSA statement).
    verify_result = verify_release(
        commit_range=commit_range,
        receipts_path=receipts_path,
        policy_path=policy_path,
        policy_preset=policy_preset,
        subject_name=subject_name,
        emit_intoto=True,
        cwd=cwd,
    )
    verification_result = str(verify_result.get("verificationResult", "UNKNOWN"))
    reason = str(verify_result.get("reason", ""))
    intoto_statement = verify_result.get("intoto_statement", {})

    # Derive subject + release name from the VSA subject when not supplied.
    subject = subject_name or ""
    if not subject and isinstance(intoto_statement, dict):
        subjects = intoto_statement.get("subject", [])
        if isinstance(subjects, list) and subjects and isinstance(subjects[0], dict):
            subject = str(subjects[0].get("name", "") or "")
    resolved_release_name = release_name or commit_range or "HEAD"

    # 2) Resolve the policy that was applied (for policy.json + report).
    if policy_preset:
        policy = load_policy(preset=policy_preset)
    elif policy_path:
        # verify_release() already validated and parsed this file above (exists,
        # not a symlink, within the size limit, a JSON object); re-read it so
        # policy.json and the digest reflect the exact policy applied.
        raw = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        policy = raw if isinstance(raw, dict) else load_policy()  # pragma: no branch
    else:
        policy = load_policy()
    policy_digest = _sha256(_canonical_json(policy))

    # 3) Load receipts (read-only) and build the evidence stream/summary.
    try:
        receipts = _load_receipts(receipts_path)
    except (FileNotFoundError, ValueError):  # pragma: no cover - verify_release
        # verify_release() already validated the path above; this is
        # defense-in-depth for a path that vanished between the two reads.
        receipts = []
    receipts_dir = receipts_path if Path(receipts_path).is_dir() else None
    evidence_stream = import_evidence_stream(receipts, receipts_dir=receipts_dir)
    evidence_summary = summarize_evidence_stream(evidence_stream)

    # 4) Assemble files (manifest computed last over all of them).
    files: "OrderedDict[str, bytes]" = OrderedDict()
    roles: Dict[str, str] = {}

    def _add(relpath: str, content: bytes, role: str) -> None:
        files[relpath] = content
        roles[relpath] = role

    # Strip the intoto wrapper from the persisted verify-release result so the
    # JSON stays a plain decision; the VSA is written separately.
    persisted_result = {
        k: v for k, v in verify_result.items() if k != "intoto_statement"
    }
    _add(_VERIFY_RELEASE_NAME, _json_bytes(persisted_result), "verify-release-result")
    _add(_VSA_NAME, _json_bytes(intoto_statement), "verification-summary-attestation")
    _add(_POLICY_NAME, _json_bytes(policy), "policy")
    _add(_EVIDENCE_STREAM_NAME, _json_bytes(evidence_stream), "evidence-stream")
    _add(_EVIDENCE_SUMMARY_NAME, _json_bytes(evidence_summary), "evidence-summary")

    for relpath, content, role in collect_receipt_artifacts(receipts_path, receipts):
        _add(relpath, content, role)

    # 5) Manifest over everything added so far.
    manifest = build_bundle_manifest(
        files=files,
        roles=roles,
        release_name=resolved_release_name,
        commit_range=commit_range,
        subject=subject,
        verification_result=verification_result,
        reason=reason,
        policy_digest=policy_digest,
        redactions=redactions,
        created_at=created_at,
    )

    # 6) Human-facing artifacts derived from the manifest + results.
    if emit_report:
        report_html = render_auditor_report_html(
            manifest=manifest,
            verify_result=persisted_result,
            policy=policy,
            evidence_summary=evidence_summary,
            redactions=redactions,
        )
        _add(_REPORT_NAME, report_html.encode("utf-8"), "auditor-report")

    _add(
        _INSTRUCTIONS_NAME,
        _render_verifier_instructions(manifest).encode("utf-8"),
        "verifier-instructions",
    )
    _add(_README_NAME, _render_bundle_readme(manifest).encode("utf-8"), "readme")

    # Re-list the manifest artifacts now that report/instructions/readme exist.
    manifest["artifacts"] = [
        {
            "path": relpath,
            "role": roles.get(relpath, "artifact"),
            "sha256": _sha256_bytes(content),
        }
        for relpath, content in files.items()
    ]

    manifest_bytes = _json_bytes(manifest)
    files[_MANIFEST_NAME] = manifest_bytes
    roles[_MANIFEST_NAME] = "manifest"

    manifest_sha = _sha256_bytes(manifest_bytes)
    files[_MANIFEST_SHA_NAME] = f"{manifest_sha}  {_MANIFEST_NAME}\n".encode("utf-8")
    roles[_MANIFEST_SHA_NAME] = "manifest-digest"

    return {
        "files": files,
        "manifest": manifest,
        "verification_result": verification_result,
        "reason": reason,
        "result_code": 0 if verification_result == "PASSED" else 1,
    }


def write_release_bundle(
    bundle: Dict[str, Any],
    output_dir: str,
    *,
    overwrite: bool = False,
) -> str:
    """Write an in-memory bundle to ``output_dir``.

    Refuses to write outside the resolved output directory (path-traversal and
    symlink-escape safe). Returns the resolved output directory path.
    """
    files = bundle.get("files", {})
    if not isinstance(files, dict) or not files:
        raise ValueError("Bundle has no files to write")

    out_path = Path(output_dir)
    if out_path.is_symlink():
        raise ValueError(f"Output directory is a symlink: {output_dir}")
    out_root = out_path.resolve()
    if out_root.exists():
        if not out_root.is_dir():
            raise ValueError(f"Output path exists and is not a directory: {output_dir}")
        if any(out_root.iterdir()) and not overwrite:
            raise ValueError(
                f"Output directory is not empty: {output_dir} "
                f"(pass overwrite=True to write into it)"
            )
    out_root.mkdir(parents=True, exist_ok=True)

    for relpath, content in files.items():
        target = (out_root / relpath).resolve()
        # Guard against traversal: every target must stay within out_root.
        # resolve() collapses any symlink in the path, so a symlink escape
        # surfaces here as an out-of-root target.
        try:
            target.relative_to(out_root)
        except ValueError as exc:
            raise ValueError(f"Refusing to write outside bundle: {relpath}") from exc
        if target.is_symlink():  # pragma: no cover - defense in depth
            raise ValueError(f"Refusing to write through a symlink: {relpath}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        target.write_bytes(content)

    return str(out_root)


def format_bundle_summary(bundle: Dict[str, Any], output_dir: str) -> str:
    """Return a short human-readable summary of a written bundle."""
    manifest = bundle.get("manifest", {})
    verification = manifest.get("verification", {})
    artifact_count = len(manifest.get("artifacts", []))
    lines = [
        "AIIR Release Evidence Bundle",
        f"  Output:        {output_dir}",
        f"  Decision:      {verification.get('result', '')} — {verification.get('reason', '')}",
        f"  Artifacts:     {artifact_count}",
        f"  Report:        {_REPORT_NAME}",
        f"  Re-verify:     {_INSTRUCTIONS_NAME}",
    ]
    return "\n".join(lines)
