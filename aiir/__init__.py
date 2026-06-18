# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
AIIR — AI Integrity Receipts

Generate cryptographic receipts for commits with declared AI involvement.
Zero dependencies — uses only Python standard library.

"""

from __future__ import annotations

__version__ = "1.7.0"

# ---------------------------------------------------------------------------
# Public API — importable via `from aiir import ...`
# ---------------------------------------------------------------------------

from aiir._canonical_cbor import (  # noqa: F401
    CANONICAL_OBJECT_SCHEMA,
    CANONICAL_OBJECT_TYPE,
    build_canonical_object_envelope,
    canonical_cbor_bytes,
    canonical_cbor_sha256,
)
from aiir._core import _canonical_json, _sha256  # noqa: F401
from aiir._detect import detect_ai_signals  # noqa: F401
from aiir._explain import explain_verification  # noqa: F401
from aiir._evidence import (  # noqa: F401
    get_receipt_evidence_tier,
    import_evidence_stream,
    normalize_receipt_to_evidence,
    summarize_evidence_stream,
)
from aiir._commitment import (  # noqa: F401
    COMMITMENT_RECEIPT_SCHEMA_VERSION,
    COMMITMENT_RECEIPT_TYPE,
    build_commitment_path_artifact,
    build_commitment_receipt,
    is_commitment_receipt,
    parse_commitment_digest_spec,
    verify_commitment_receipt,
)
from aiir._ledger import append_to_ledger, export_ledger  # noqa: F401
from aiir._policy import (
    evaluate_ledger_policy,
    evaluate_receipt_policy,
    load_policy,
    POLICY_PRESETS,
)  # noqa: F401
from aiir._receipt import (
    generate_receipt,
    generate_receipts_for_range,
    format_receipt_pretty,
    wrap_in_toto_statement,
    build_review_receipt,
    REVIEW_RECEIPT_SCHEMA_VERSION,
)  # noqa: F401
from aiir._schema import validate_receipt_schema as validate_receipt  # noqa: F401
from aiir._stats import check_policy, format_badge, format_stats  # noqa: F401
from aiir._verify import verify_receipt, verify_receipt_file  # noqa: F401
from aiir._transparency import (  # noqa: F401
    parse_witness_quorum,
    validate_rekor_bundle_schema,
    validate_trust_root_schema,
    verify_transparency_material,
)
from aiir._verify_inference import (  # noqa: F401
    is_inference_receipt,
    verify_inference_receipt,
    verify_inference_chain,
    verify_inference_receipt_file,
)
from aiir._verify_research_evidence import (  # noqa: F401
    is_research_evidence_receipt,
    verify_research_evidence_receipt,
    verify_research_evidence_receipt_set,
    verify_research_evidence_receipt_file,
)
from aiir._verify_cbor import (  # noqa: F401
    CborDecodeError,
    decode_cbor_full,
    verify_cbor_envelope,
    verify_cbor_file,
    verify_cbor_sidecar,
)
from aiir._verify_release import (  # noqa: F401
    verify_release,
    format_release_report,
    VSA_PREDICATE_TYPE,
)
from aiir._release_bundle import (  # noqa: F401
    BUNDLE_SCHEMA,
    build_release_bundle,
    render_auditor_report_html,
    write_release_bundle,
)
from aiir._github import (  # noqa: F401
    format_github_summary,
    create_check_run,
    post_pr_comment,
    format_commit_trailer,
)
from aiir._gitlab import (  # noqa: F401
    format_gitlab_summary,
    format_gl_sast_report,
    generate_dashboard_html,
    parse_webhook_event,
    validate_webhook_token,
    build_receipts_graphql_query,
    enforce_approval_rules,
)

__all__ = [
    "__version__",
    # Receipt generation
    "generate_receipt",
    "generate_receipts_for_range",
    "format_receipt_pretty",
    "wrap_in_toto_statement",
    "build_review_receipt",
    "REVIEW_RECEIPT_SCHEMA_VERSION",
    # Detection
    "detect_ai_signals",
    "COMMITMENT_RECEIPT_SCHEMA_VERSION",
    "COMMITMENT_RECEIPT_TYPE",
    "build_commitment_path_artifact",
    "build_commitment_receipt",
    "is_commitment_receipt",
    "parse_commitment_digest_spec",
    "verify_commitment_receipt",
    # Verification
    "verify_receipt",
    "verify_receipt_file",
    "is_research_evidence_receipt",
    "verify_research_evidence_receipt",
    "verify_research_evidence_receipt_set",
    "verify_research_evidence_receipt_file",
    "verify_transparency_material",
    "parse_witness_quorum",
    "validate_rekor_bundle_schema",
    "validate_trust_root_schema",
    "explain_verification",
    "get_receipt_evidence_tier",
    "normalize_receipt_to_evidence",
    "import_evidence_stream",
    "summarize_evidence_stream",
    # CBOR verification
    "CborDecodeError",
    "decode_cbor_full",
    "verify_cbor_envelope",
    "verify_cbor_file",
    "verify_cbor_sidecar",
    # Release verification
    "verify_release",
    "format_release_report",
    "VSA_PREDICATE_TYPE",
    # Release evidence bundle
    "BUNDLE_SCHEMA",
    "build_release_bundle",
    "write_release_bundle",
    "render_auditor_report_html",
    # Schema
    "validate_receipt",
    # Ledger
    "append_to_ledger",
    "export_ledger",
    # Stats & policy
    "format_badge",
    "format_stats",
    "check_policy",
    "load_policy",
    "evaluate_receipt_policy",
    "evaluate_ledger_policy",
    "POLICY_PRESETS",
    # GitHub integration
    "format_github_summary",
    "create_check_run",
    "post_pr_comment",
    "format_commit_trailer",
    # GitLab integration
    "format_gitlab_summary",
    "format_gl_sast_report",
    "generate_dashboard_html",
    "parse_webhook_event",
    "validate_webhook_token",
    "build_receipts_graphql_query",
    "enforce_approval_rules",
    # Low-level (for third-party implementors)
    "CANONICAL_OBJECT_SCHEMA",
    "CANONICAL_OBJECT_TYPE",
    "build_canonical_object_envelope",
    "canonical_cbor_bytes",
    "canonical_cbor_sha256",
    "_canonical_json",
    "_sha256",
    # Quantum workload provenance
    "quantum",
]
