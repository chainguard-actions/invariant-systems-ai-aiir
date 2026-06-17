#!/usr/bin/env python3
"""Generate hardened conformance test vectors for AIIR.

Produces five new vector files:
  1. adversarial_conformance_vectors.json  — hostile receipts promoted from corpus
  2. unicode_evasion_vectors.json          — Unicode attack patterns
  3. canonicalization_trap_vectors.json     — encoder traps
  4. cross_format_vectors.json             — JSON↔CBOR determinism
  5. negative_encoding_vectors.json        — known misencoding traps

These complement the existing 25 conformance + 8 encoder interop vectors,
giving third-party implementers a hardened test wall.

Run from repo root:
    python schemas/test-vectors/generate_hardened_vectors.py

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from aiir._core import _canonical_json, _sha256  # noqa: E402

try:
    from aiir._receipt import _canonical_receipt_cbor_bytes  # noqa: E402

    HAS_CBOR = True
except ImportError:
    HAS_CBOR = False

OUTPUT_DIR = os.path.dirname(__file__)
SCHEMAS_DIR = os.path.join(os.path.dirname(__file__), "..")

CORE_KEYS = {"type", "schema", "version", "commit", "ai_attestation", "provenance"}
TIMESTAMP = "2026-03-25T00:00:00Z"


# ── Helpers ────────────────────────────────────────────────────────


def _base_core(**overrides):
    """Minimal valid core with optional field overrides."""
    core = {
        "type": "aiir.commit_receipt",
        "schema": "aiir/commit_receipt.v1",
        "version": "1.0.12",
        "commit": {
            "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "author": {
                "name": "Alice",
                "email": "alice@example.com",
                "date": "2026-03-09T00:00:00Z",
            },
            "committer": {
                "name": "Alice",
                "email": "alice@example.com",
                "date": "2026-03-09T00:00:00Z",
            },
            "subject": "feat: add widget",
            "message_hash": "sha256:375aca2c5a71c7ffaaa0c3602ed0f82d27986ce0776b5c5c1bc2d2a5638b18bb",
            "diff_hash": "sha256:a9b7bc7b29f22a8b1ae213c4105d73c39b9e3f218d75bb6a288207c1d86b96fe",
            "files_changed": 1,
            "files": ["widget.py"],
        },
        "ai_attestation": {
            "is_ai_authored": False,
            "signals_detected": [],
            "signal_count": 0,
            "is_bot_authored": False,
            "bot_signals_detected": [],
            "bot_signal_count": 0,
            "authorship_class": "human",
            "detection_method": "heuristic_v2",
        },
        "provenance": {
            "repository": "https://github.com/example/repo",
            "tool": "https://github.com/invariant-systems-ai/aiir@1.0.12",
            "generator": "aiir.cli",
        },
    }
    # Apply nested overrides
    for key, value in overrides.items():
        parts = key.split(".")
        target = core
        for p in parts[:-1]:
            target = target[p]
        target[parts[-1]] = value
    return core


def _compute(core):
    """Compute canonical JSON, content_hash, receipt_id from core dict."""
    only_core = {k: v for k, v in core.items() if k in CORE_KEYS}
    cj = _canonical_json(only_core)
    h = _sha256(cj)
    return {
        "canonical_json": cj,
        "canonical_json_sha256": h,
        "content_hash": f"sha256:{h}",
        "receipt_id": f"g1-{h[:32]}",
    }


def _full_receipt(core, computed):
    """Build a complete receipt from core + computed values."""
    return {
        **core,
        "receipt_id": computed["receipt_id"],
        "content_hash": computed["content_hash"],
        "timestamp": TIMESTAMP,
        "extensions": {},
    }


def _valid_vector(vid, description, core, notes=""):
    """Build a vector for a valid receipt."""
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vec = {
        "id": vid,
        "description": description,
        "receipt": receipt,
        "expected": {
            "valid": True,
            "errors": [],
        },
        "computed": computed,
    }
    if notes:
        vec["implementation_notes"] = notes
    return vec


def _invalid_vector(vid, description, receipt, error_contains="", notes=""):
    """Build a vector for an invalid receipt that MUST be rejected."""
    vec = {
        "id": vid,
        "description": description,
        "receipt": receipt,
        "expected": {
            "valid": False,
            "must_reject": True,
        },
    }
    if error_contains:
        vec["expected"]["error_pattern"] = error_contains
    if notes:
        vec["implementation_notes"] = notes
    return vec


def _encoder_vector(vid, description, core, notes=""):
    """Build an encoder interop vector with expected canonical JSON + hash."""
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vec = {
        "id": vid,
        "description": description,
        "input_core": core,
        "expected": computed,
        "full_receipt": receipt,
    }
    if notes:
        vec["implementation_notes"] = notes
    # Add CBOR if available
    if HAS_CBOR:
        try:
            cbor_bytes = _canonical_receipt_cbor_bytes(receipt)
            vec["expected"]["cbor_hex"] = cbor_bytes.hex()
            vec["expected"]["cbor_sha256"] = hashlib.sha256(cbor_bytes).hexdigest()
            vec["expected"]["cbor_length"] = len(cbor_bytes)
        except Exception:
            pass
    return vec


# ═══════════════════════════════════════════════════════════════════
# FILE 1: Adversarial conformance vectors
# Promoted from tests/adversarial/corpus.json — the best 15 attacks
# that any third-party verifier MUST handle correctly.
# ═══════════════════════════════════════════════════════════════════


def _build_adversarial_vectors():
    vectors = []

    # --- Injection attacks ---

    # adv-cf-01: HTML in version field
    core = _base_core()
    core["version"] = '<script>alert("xss")</script>'
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _invalid_vector(
            "adv-cf-01-html-version-injection",
            "HTML script tag in version field — MUST be rejected by version format check before hash computation",
            receipt,
            error_contains="version",
            notes="Even though the hash is 'correct' for this payload, the version field must be validated before hash check. Spec §7.",
        )
    )

    # adv-cf-02: Null byte in subject
    core = _base_core(**{"commit.subject": "feat: add widget\x00; DROP TABLE receipts"})
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _valid_vector(
            "adv-cf-02-null-byte-in-subject",
            "Null byte in commit subject — receipt is structurally valid (hash covers the null byte); implementers should sanitize display",
            core,
            notes="The null byte is part of the canonical JSON. Verifiers must not strip it before hashing. Display layers should sanitize.",
        )
    )

    # adv-cf-03: Bidi override in author name
    core = _base_core(
        **{"commit.author.name": "\u202eecilA"}
    )  # U+202E RIGHT-TO-LEFT OVERRIDE
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _valid_vector(
            "adv-cf-03-bidi-override-author",
            "Unicode bidi override (U+202E) in author name — receipt is valid but implementers should flag visual spoofing risk",
            core,
            notes="RLO character makes 'ecilA' display as 'Alice' in RTL context. Receipt is valid because the hash covers the bytes as-is. Detection/display layers should warn.",
        )
    )

    # adv-cf-04: CRLF in file path
    core = _base_core(**{"commit.files": ["normal.py", "evil\r\nX-Injected: true"]})
    core["commit"]["files_changed"] = 2
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _valid_vector(
            "adv-cf-04-crlf-in-file-path",
            "CRLF injection in file path — receipt is valid; hash covers the literal CRLF bytes; HTTP layers must sanitize",
            core,
            notes="File paths can contain arbitrary bytes from git. The verifier must not normalize them. Transport layers must escape.",
        )
    )

    # adv-cf-05: Zero-width space in authorship_class
    core = _base_core(**{"ai_attestation.authorship_class": "hu\u200bman"})  # ZWSP
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _valid_vector(
            "adv-cf-05-zwsp-authorship-class",
            "Zero-width space (U+200B) in authorship_class — receipt is valid but the class will NOT match 'human' in equality checks",
            core,
            notes="This is a detection evasion attack. The hash is correct for the ZWSP-containing value. Policy layers must normalize before comparing authorship_class values.",
        )
    )

    # adv-cf-06: Path traversal in files
    core = _base_core(**{"commit.files": ["../../etc/passwd"]})
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _valid_vector(
            "adv-cf-06-path-traversal-files",
            "Path traversal in files array — receipt is valid; file paths are metadata not filesystem operations",
            core,
            notes="Verifiers must never use file paths from receipts for filesystem operations. They are commit metadata only.",
        )
    )

    # --- Tampering attacks ---

    # adv-cf-07: Single bit flip in content_hash
    core = _base_core()
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    good_hash = receipt["content_hash"]
    # Flip last hex char
    flipped = good_hash[:-1] + ("0" if good_hash[-1] != "0" else "1")
    receipt["content_hash"] = flipped
    vectors.append(
        _invalid_vector(
            "adv-cf-07-bit-flip-content-hash",
            "Single character change in content_hash — MUST fail hash comparison",
            receipt,
            error_contains="content hash",
            notes="Tests that verification uses exact comparison, not prefix matching.",
        )
    )

    # adv-cf-08: Swap content_hash and receipt_id
    core = _base_core()
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    receipt["content_hash"], receipt["receipt_id"] = (
        receipt["receipt_id"],
        receipt["content_hash"],
    )
    vectors.append(
        _invalid_vector(
            "adv-cf-08-swap-hash-and-id",
            "content_hash and receipt_id swapped — both checks MUST fail",
            receipt,
            notes="Tests that verifier checks both fields independently, not just one.",
        )
    )

    # adv-cf-09: Tamper AI flag without rehashing
    core = _base_core()
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    receipt["ai_attestation"]["is_ai_authored"] = True  # was False
    vectors.append(
        _invalid_vector(
            "adv-cf-09-flip-ai-flag-no-rehash",
            "is_ai_authored flipped from false to true without recomputing content_hash — MUST detect tampering",
            receipt,
            error_contains="content hash",
            notes="Common attestation fraud: flip the AI flag after receipt generation. The content hash must catch this.",
        )
    )

    # adv-cf-10: Truncated content_hash
    core = _base_core()
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    receipt["content_hash"] = receipt["content_hash"][:20]  # truncate
    vectors.append(
        _invalid_vector(
            "adv-cf-10-truncated-content-hash",
            "content_hash truncated to 20 chars — MUST reject incomplete hash",
            receipt,
            error_contains="content hash",
            notes="Hash comparison must check full length. Truncated hashes are a collision risk.",
        )
    )

    # adv-cf-11: md5 prefix on content_hash
    core = _base_core()
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    receipt["content_hash"] = "md5:" + computed["canonical_json_sha256"]
    vectors.append(
        _invalid_vector(
            "adv-cf-11-wrong-hash-algorithm",
            "content_hash uses md5: prefix instead of sha256: — MUST reject wrong algorithm",
            receipt,
            error_contains="content hash",
            notes="Algorithm downgrade attack. Verifiers must reject anything except sha256: prefix.",
        )
    )

    # --- Bypass attacks ---

    # adv-cf-12: Valid hash but wrong type
    core = _base_core()
    core["type"] = "evil.commit_receipt"
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _invalid_vector(
            "adv-cf-12-wrong-type-valid-hash",
            "Receipt with valid content_hash but wrong type — type check MUST precede hash check",
            receipt,
            error_contains="type",
            notes="If the verifier checks hash before type, an attacker could craft receipts that look valid but aren't AIIR receipts.",
        )
    )

    # adv-cf-13: Valid hash but non-aiir schema
    core = _base_core()
    core["schema"] = "evil/commit_receipt.v1"
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        _invalid_vector(
            "adv-cf-13-wrong-schema-prefix",
            "Receipt with valid hash but schema not starting with 'aiir/' — schema check MUST precede hash check",
            receipt,
            error_contains="schema",
            notes="Schema prefix validation prevents cross-protocol receipt confusion.",
        )
    )

    # adv-cf-14: Replay (exact duplicate)
    core = _base_core()
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        {
            "id": "adv-cf-14-exact-replay",
            "description": "Exact duplicate receipt — content-addressed means same ID is expected; dedup is a policy decision, not a verification failure",
            "receipt": receipt,
            "expected": {
                "valid": True,
                "errors": [],
            },
            "implementation_notes": "Two receipts with the same content_hash are not a verification error. Replay/dedup protection is a ledger-level (policy) concern, not a receipt-level concern.",
        }
    )

    # adv-cf-15: Embedded credentials in repository URL
    core = _base_core(
        **{"provenance.repository": "https://user:p4ssw0rd@github.com/example/repo"}
    )
    computed = _compute(core)
    receipt = _full_receipt(core, computed)
    vectors.append(
        {
            "id": "adv-cf-15-creds-in-url",
            "description": "Repository URL with embedded credentials — receipt is structurally valid; implementers SHOULD strip or warn about credentials",
            "receipt": receipt,
            "expected": {
                "valid": True,
                "errors": [],
            },
            "computed": _compute(core),
            "implementation_notes": "Verifiers should not reject based on URL content, but display layers should redact credentials. The reference implementation strips credentials before storage.",
        }
    )

    return vectors


# ═══════════════════════════════════════════════════════════════════
# FILE 2: Unicode evasion vectors
# Attack patterns that try to fool detection or break canonicalization.
# ═══════════════════════════════════════════════════════════════════


def _build_unicode_vectors():
    vectors = []

    # --- Homoglyph attacks: visually identical but different bytes ---

    # uni-01: Cyrillic 'а' (U+0430) looks like Latin 'a'
    core = _base_core(**{"commit.author.name": "\u0430lice"})  # Cyrillic а + "lice"
    vectors.append(
        _encoder_vector(
            "uni-01-cyrillic-a-homoglyph",
            "Author name with Cyrillic 'а' (U+0430) instead of Latin 'a' — visually identical, different bytes, different hash",
            core,
            notes="Canonical JSON with ensure_ascii=True encodes U+0430 as \\u0430. A naive implementation that doesn't escape non-ASCII would produce a different hash.",
        )
    )

    # uni-02: Greek 'Α' (U+0391) looks like Latin 'A'
    core = _base_core(**{"commit.subject": "feat: \u0391dd widget"})  # Greek Alpha
    vectors.append(
        _encoder_vector(
            "uni-02-greek-alpha-homoglyph",
            "Subject with Greek 'Α' (U+0391) instead of Latin 'A' — homoglyph in commit subject changes hash",
            core,
            notes="After NFKC normalization, U+0391 stays as U+0391 (Greek Alpha). This is a different codepoint than Latin 'A' (U+0041). Detection normalization (TR39 confusable resolution) maps it to 'A' for signal matching, but the canonical JSON preserves the original bytes.",
        )
    )

    # uni-03: Fullwidth Latin 'Ａ' (U+FF21)
    core = _base_core(**{"commit.author.name": "\uff21lice"})  # Fullwidth A
    vectors.append(
        _encoder_vector(
            "uni-03-fullwidth-latin-homoglyph",
            "Author name with fullwidth 'Ａ' (U+FF21) instead of ASCII 'A' — NFKC normalizes this to ASCII 'A' but canonical JSON preserves original bytes",
            core,
            notes="NFKC normalization converts U+FF21 to U+0041 (ASCII A). But canonical JSON operates on the ORIGINAL string, not the normalized form. Implementations must not NFKC-normalize before hashing.",
        )
    )

    # uni-04: Armenian 'Ꭺ' (U+13AA, Cherokee A) looks like Latin 'A'
    core = _base_core(**{"commit.author.name": "\u13aalice"})  # Cherokee A
    vectors.append(
        _encoder_vector(
            "uni-04-cherokee-a-homoglyph",
            "Author name with Cherokee 'Ꭺ' (U+13AA) instead of Latin 'A' — obscure homoglyph",
            core,
            notes="Cherokee A is a less common confusable. Tests that ensure_ascii encoding handles Supplementary Multilingual Plane characters via \\uXXXX escaping.",
        )
    )

    # --- Invisible character attacks ---

    # uni-05: Zero-width joiner between letters
    core = _base_core(**{"commit.subject": "feat: add\u200dwidget"})  # ZWJ
    vectors.append(
        _encoder_vector(
            "uni-05-zero-width-joiner",
            "Subject with zero-width joiner (U+200D) between words — invisible but changes hash",
            core,
            notes="ZWJ is invisible in most renderers. The canonical JSON encodes it as \\u200d. An implementation that strips invisible chars before hashing will get a different hash.",
        )
    )

    # uni-06: Soft hyphen in author name
    core = _base_core(**{"commit.author.name": "Al\u00adice"})  # SOFT HYPHEN
    vectors.append(
        _encoder_vector(
            "uni-06-soft-hyphen",
            "Author name with soft hyphen (U+00AD) — invisible in most fonts, changes hash",
            core,
            notes="Soft hyphen is often stripped by display layers but must be preserved in canonical JSON for correct hashing.",
        )
    )

    # uni-07: Combining marks on normal characters
    core = _base_core(
        **{"commit.author.name": "A\u0300lice"}
    )  # A + COMBINING GRAVE ACCENT
    vectors.append(
        _encoder_vector(
            "uni-07-combining-grave-accent",
            "Author name with combining grave accent (U+0300) on 'A' — not the precomposed 'À' (U+00C0)",
            core,
            notes="NFC normalization would compose A+U+0300 into U+00C0 (À). Canonical JSON must NOT NFC-normalize; it preserves the decomposed form. The hash differs from a receipt that used precomposed À.",
        )
    )

    # uni-08: Variation selector
    core = _base_core(
        **{"commit.subject": "feat: add widget\ufe0f"}
    )  # VS16 (emoji presentation)
    vectors.append(
        _encoder_vector(
            "uni-08-variation-selector",
            "Subject with variation selector VS16 (U+FE0F) appended — invisible modifier, changes hash",
            core,
            notes="Variation selectors are invisible in plain text contexts but change the byte content. Implementations must preserve them in canonical JSON.",
        )
    )

    return vectors


# ═══════════════════════════════════════════════════════════════════
# FILE 3: Canonicalization trap vectors
# Edge cases that trip up cross-language JSON encoders.
# ═══════════════════════════════════════════════════════════════════


def _build_canonicalization_vectors():
    vectors = []

    # can-01: Mixed-case keys sorting
    # Python sorts uppercase before lowercase (A < a in ASCII)
    core = _base_core()
    core["commit"]["Zebra_field"] = "should sort after all lowercase keys"
    vectors.append(
        _encoder_vector(
            "can-01-mixed-case-key-sort",
            "Commit has an extra uppercase key 'Zebra_field' — tests ASCII sort order where uppercase (0x5A) < lowercase (0x61)",
            core,
            notes="In ASCII/UTF-8 sorting: 'Z' (0x5A) < 'a' (0x61). So 'Zebra_field' sorts BEFORE 'author'. Some languages default to locale-aware sorting which would produce a different order.",
        )
    )

    # can-02: Integer 0 vs boolean false vs null
    # All three are different JSON values: 0, false, null
    core_zero = _base_core()
    core_zero["commit"]["files_changed"] = 0
    core_zero["ai_attestation"]["signal_count"] = 0
    vectors.append(
        _encoder_vector(
            "can-02-zero-vs-false-vs-null",
            "files_changed=0, signal_count=0 — integer zero must encode as '0', not 'false' or 'null'",
            core_zero,
            notes="In weakly typed languages: 0, false, null may be confused. JSON requires: 0 → '0', false → 'false', null → 'null'. All produce different bytes and different hashes.",
        )
    )

    # can-03: Boolean vs integer in typed fields
    core_bool = _base_core()
    # is_ai_authored must be JSON boolean, not 0/1
    vectors.append(
        _encoder_vector(
            "can-03-boolean-not-integer",
            "is_ai_authored=false — must encode as 'false', not '0' or 'null' or empty string",
            core_bool,
            notes="Some serializers coerce booleans to integers. JSON canonical form requires literal 'false'/'true'.",
        )
    )

    # can-04: null vs absent key
    core_null = _base_core(**{"provenance.repository": None})
    vectors.append(
        _encoder_vector(
            "can-04-null-vs-absent",
            "repository=null — 'null' value is different from absent key; both must be encoded correctly",
            core_null,
            notes="A present key with null value serializes as '\"repository\":null'. An absent key produces no output. These yield different canonical JSON and different hashes.",
        )
    )

    # can-05: Recursive key sorting (nested objects)
    # Keys within commit.author must also be sorted
    core_nested = _base_core()
    # Force creation with intentionally disordered keys
    core_nested["commit"]["author"] = {
        "name": "Alice",
        "email": "alice@example.com",
        "date": "2026-03-09T00:00:00Z",
    }
    vectors.append(
        _encoder_vector(
            "can-05-recursive-key-sort",
            "Nested keys in commit.author must be sorted recursively — date < email < name",
            core_nested,
            notes="Canonical JSON requires ALL objects to have sorted keys, not just the top level. Verify that commit.author has keys in order: date, email, name.",
        )
    )

    # can-06: Empty string vs null vs absent
    core_empty = _base_core(**{"provenance.repository": ""})
    vectors.append(
        _encoder_vector(
            "can-06-empty-string-vs-null",
            "repository='' (empty string) — different from null and from absent key",
            core_empty,
            notes='Empty string serializes as \'"repository":""\'. Null serializes as \'"repository":null\'. These produce different hashes.',
        )
    )

    # can-07: Backslash and quote escaping in strings
    core_esc = _base_core(**{"commit.subject": 'feat: handle "quotes" and \\backslash'})
    vectors.append(
        _encoder_vector(
            "can-07-backslash-quote-escaping",
            'Subject contains literal double quotes and backslash — must be escaped as \\" and \\\\ in canonical JSON',
            core_esc,
            notes='JSON spec requires: " → \\", \\ → \\\\. Verify the canonical JSON has correct escaping.',
        )
    )

    # can-08: Control characters in string values
    core_ctrl = _base_core(**{"commit.subject": "feat:\ttab\nnewline\rreturn"})
    vectors.append(
        _encoder_vector(
            "can-08-control-char-escaping",
            "Subject contains tab, newline, carriage return — must be escaped as \\t, \\n, \\r in canonical JSON",
            core_ctrl,
            notes="JSON spec requires control chars to be escaped. Tab=\\t, LF=\\n, CR=\\r. Some encoders use \\u000a instead of \\n — both are valid JSON but produce different bytes. Canonical JSON uses the short escapes.",
        )
    )

    return vectors


# ═══════════════════════════════════════════════════════════════════
# FILE 4: Cross-format determinism vectors
# Same receipt in JSON and CBOR — content_hash MUST match.
# ═══════════════════════════════════════════════════════════════════


def _build_cross_format_vectors():
    if not HAS_CBOR:
        print(
            "WARNING: CBOR support not available. Cross-format vectors will lack CBOR data."
        )
        print("  Install aiir with CBOR support to generate complete vectors.")

    vectors = []

    # Five receipts of increasing complexity
    cases = [
        (
            "xfmt-01-simple-human",
            "Simple human receipt — JSON and CBOR must produce same content_hash",
            {},
        ),
        (
            "xfmt-02-ai-with-signals",
            "AI-assisted receipt with signals — cross-format determinism",
            {
                "ai_attestation.is_ai_authored": True,
                "ai_attestation.signals_detected": ["co-author: GitHub Copilot"],
                "ai_attestation.signal_count": 1,
                "ai_attestation.authorship_class": "ai_assisted",
            },
        ),
        (
            "xfmt-03-unicode-heavy",
            "Receipt with Unicode in all string fields — cross-format",
            {
                "commit.author.name": "\u00c9milie Dupont-L\u00e9ger",
                "commit.subject": "feat: ajouter \u00e9diteur \u2014 v2",
            },
        ),
        (
            "xfmt-04-null-repo",
            "Receipt with null repository — cross-format null encoding",
            {
                "provenance.repository": None,
            },
        ),
        (
            "xfmt-05-many-files",
            "Receipt with 50 files — cross-format array encoding",
            {
                "commit.files": [f"src/module_{i:02d}.py" for i in range(50)],
                "commit.files_changed": 50,
            },
        ),
    ]

    for vid, desc, overrides in cases:
        core = _base_core(**overrides)
        computed = _compute(core)
        receipt = _full_receipt(core, computed)

        vec = {
            "id": vid,
            "description": desc,
            "receipt": receipt,
            "json_content_hash": computed["content_hash"],
            "json_receipt_id": computed["receipt_id"],
            "json_canonical": computed["canonical_json"],
        }

        if HAS_CBOR:
            try:
                cbor_bytes = _canonical_receipt_cbor_bytes(receipt)
                vec["cbor_hex"] = cbor_bytes.hex()
                vec["cbor_sha256"] = hashlib.sha256(cbor_bytes).hexdigest()
                vec["cbor_length"] = len(cbor_bytes)
            except Exception as e:
                vec["cbor_error"] = str(e)

        vec["assertion"] = (
            "content_hash computed from canonical JSON of CORE_KEYS must be identical regardless of whether the receipt was decoded from JSON or CBOR wire format"
        )
        vectors.append(vec)

    return vectors


# ═══════════════════════════════════════════════════════════════════
# FILE 5: Negative encoding vectors
# "Here's the WRONG canonical JSON and here's the RIGHT one"
# ═══════════════════════════════════════════════════════════════════


def _build_negative_encoding_vectors():
    vectors = []

    core = _base_core()
    correct = _compute(core)

    # neg-01: Unsorted keys
    only_core = {k: v for k, v in core.items() if k in CORE_KEYS}
    # Python dicts since 3.7 are insertion-ordered but our base_core isn't alphabetical at top level
    # Manually construct a known-wrong ordering
    wrong_json = (
        '{"version":"1.0.12","type":"aiir.commit_receipt"'  # deliberately wrong order
    )
    vectors.append(
        {
            "id": "neg-01-unsorted-keys",
            "description": "WRONG: top-level keys in insertion order instead of sorted — the hash would be different",
            "correct_canonical_json": correct["canonical_json"],
            "correct_content_hash": correct["content_hash"],
            "wrong_approach": "Using insertion-order key serialization instead of sort_keys=True",
            "wrong_canonical_json_prefix": wrong_json,
            "trap": "Python dicts preserve insertion order since 3.7, so json.dumps() without sort_keys=True may produce different output on different Python versions or when keys are inserted in different orders.",
            "implementation_notes": "Always use sort_keys=True (Python), keys().sort() (JS), or equivalent. Key ordering must be pure ASCII/byte ordering.",
        }
    )

    # neg-02: Pretty-printed (with whitespace)
    wrong_pretty = json.dumps(only_core, ensure_ascii=True, sort_keys=True, indent=2)
    vectors.append(
        {
            "id": "neg-02-whitespace-in-canonical",
            "description": "WRONG: canonical JSON with indent/whitespace — spaces change the hash",
            "correct_canonical_json": correct["canonical_json"],
            "correct_content_hash": correct["content_hash"],
            "wrong_canonical_json_prefix": wrong_pretty[:100] + "...",
            "wrong_content_hash": f"sha256:{_sha256(wrong_pretty)}",
            "trap": "json.dumps() defaults to separators=(', ', ': ') in Python (note spaces). Canonical JSON requires separators=(',', ':') — no spaces.",
            "implementation_notes": "Use separators=(',', ':') in Python. In JS, JSON.stringify(obj) with no space argument. Verify no whitespace between tokens.",
        }
    )

    # neg-03: Non-ASCII not escaped
    core_uni = _base_core(**{"commit.author.name": "\u00c9milie"})
    correct_uni = _compute(core_uni)
    only_uni = {k: v for k, v in core_uni.items() if k in CORE_KEYS}
    wrong_no_escape = json.dumps(
        only_uni, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    vectors.append(
        {
            "id": "neg-03-non-ascii-unescaped",
            "description": "WRONG: Unicode chars left as UTF-8 instead of \\uXXXX escaped — different bytes, different hash",
            "correct_canonical_json_contains": "\\u00c9milie",
            "correct_content_hash": correct_uni["content_hash"],
            "wrong_canonical_json_contains": "\u00c9milie",
            "wrong_content_hash": f"sha256:{_sha256(wrong_no_escape)}",
            "trap": "In Python, json.dumps(ensure_ascii=False) writes raw UTF-8. Canonical JSON requires ensure_ascii=True. In JS, JSON.stringify() does NOT escape non-ASCII by default — you must post-process.",
            "implementation_notes": "Python: ensure_ascii=True. JS: JSON.stringify() then replace non-ASCII with \\uXXXX. Go: use json.Marshal which escapes by default.",
        }
    )

    # neg-04: NFC normalization before hashing
    core_decomposed = _base_core(
        **{"commit.author.name": "A\u0300lice"}
    )  # decomposed À
    correct_decomposed = _compute(core_decomposed)
    import unicodedata

    core_nfc = copy.deepcopy(core_decomposed)
    core_nfc["commit"]["author"]["name"] = unicodedata.normalize(
        "NFC", core_decomposed["commit"]["author"]["name"]
    )
    wrong_nfc = _compute(core_nfc)
    vectors.append(
        {
            "id": "neg-04-nfc-normalization-before-hash",
            "description": "WRONG: NFC-normalizing string values before hashing — the decomposed form (A + U+0300) and composed form (U+00C0) produce different hashes",
            "decomposed_input": "A\\u0300lice (A + COMBINING GRAVE ACCENT)",
            "composed_equivalent": "\\u00c0lice (LATIN CAPITAL LETTER A WITH GRAVE)",
            "correct_content_hash": correct_decomposed["content_hash"],
            "wrong_content_hash_if_nfc": wrong_nfc["content_hash"],
            "hashes_differ": correct_decomposed["content_hash"]
            != wrong_nfc["content_hash"],
            "trap": "Some languages or libraries NFC-normalize input strings automatically. Canonical JSON must preserve the original byte sequence. Do NOT normalize before hashing.",
            "implementation_notes": "The detection layer uses NFKC + TR39 confusable resolution for signal matching. The canonical JSON layer must NOT normalize. These are separate concerns.",
        }
    )

    return vectors


# ═══════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════


def _write(filename, description, vectors, output_dir):
    output = {
        "$schema": f"https://invariantsystems.io/schemas/aiir/{filename.replace('.json', '')}.v1",
        "description": description,
        "spec_version": "2.0.0",
        "generated_by": "schemas/test-vectors/generate_hardened_vectors.py",
        "generated_at": TIMESTAMP,
        "count": len(vectors),
        "vectors": vectors,
    }
    outpath = os.path.join(output_dir, filename)
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=True)
        f.write("\n")
    print(f"  {len(vectors):2d} vectors → {outpath}")
    return len(vectors)


def main():
    print("Generating hardened conformance vectors...")
    print()

    total = 0

    adv = _build_adversarial_vectors()
    total += _write(
        "adversarial_conformance_vectors.json",
        "AIIR adversarial conformance vectors. Third-party verifiers MUST handle every vector correctly — rejecting invalid receipts and accepting structurally valid ones even when the content is hostile.",
        adv,
        SCHEMAS_DIR,
    )

    uni = _build_unicode_vectors()
    total += _write(
        "unicode_evasion_vectors.json",
        "AIIR Unicode evasion test vectors. Each vector contains a homoglyph, invisible character, or Unicode edge case. Conforming implementations MUST produce identical canonical_json, content_hash, and receipt_id for each vector's input_core.",
        uni,
        SCHEMAS_DIR,
    )

    canon = _build_canonicalization_vectors()
    total += _write(
        "canonicalization_trap_vectors.json",
        "AIIR canonicalization trap vectors. Edge cases that commonly differ across JSON encoders in different languages. Conforming implementations MUST produce identical canonical_json, content_hash, and receipt_id.",
        canon,
        SCHEMAS_DIR,
    )

    xfmt = _build_cross_format_vectors()
    total += _write(
        "cross_format_vectors.json",
        "AIIR cross-format determinism vectors. The same receipt in JSON and CBOR must yield the same content_hash. Tests that encoding (JSON vs CBOR) is orthogonal to content identity.",
        xfmt,
        SCHEMAS_DIR,
    )

    neg = _build_negative_encoding_vectors()
    total += _write(
        "negative_encoding_vectors.json",
        "AIIR negative encoding vectors. Each vector shows a WRONG way to produce canonical JSON and the CORRECT way. Implementers can test their encoder against known misencoding traps.",
        neg,
        SCHEMAS_DIR,
    )

    print()
    print(f"Total: {total} new hardened vectors across 5 files.")
    print()
    print("Existing conformance vectors:")
    print("  25 — schemas/test_vectors.json")
    print("  24 — schemas/cbor_test_vectors.json")
    print("   8 — schemas/test-vectors/encoder_interop_vectors.json")
    print(f"Grand total: {total + 25 + 24 + 8} published conformance vectors")


if __name__ == "__main__":
    main()
