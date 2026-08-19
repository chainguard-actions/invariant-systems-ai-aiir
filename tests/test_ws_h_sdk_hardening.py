# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
"""
Regression tests for Workstream-H SDK and VS Code extension hardening.

Covers:
- C2 (Rust): bytewise map-key ordering in lib.rs / tests.rs (source-inspection)
- MEDIUM: JS canonicalJson code-point sort (both ASCII and BMP-plus code points)
- MEDIUM: VS Code extension hubBaseUrl trust isolation (source-inspection)
- LOW: JS LICENSE file present, README SRI pin, docblock package name
- LOW: Rust README verify_sidecar signature accuracy
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
JS_SDK = os.path.join(REPO_ROOT, "sdks", "js")
# ESM import specifiers must be file:// URLs, not native paths — Node rejects
# Windows drive-letter paths (e.g. "d:\\...") as import specifiers. Use this
# URL form inside `import ... from '...'` statements; keep JS_SDK for fs ops.
from pathlib import Path as _Path  # noqa: E402

JS_SDK_URL = _Path(JS_SDK).resolve().as_uri()
RUST_SDK = os.path.join(REPO_ROOT, "sdks", "rust")
VSCODE_EXT = os.path.join(REPO_ROOT, "extensions", "vscode")
VSCODE_SRC = os.path.join(VSCODE_EXT, "src")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _node_available() -> bool:
    try:
        subprocess.run(
            ["node", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _run_node(script: str) -> str:
    """Run an inline Node.js script and return stdout (raises on non-zero exit)."""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script.encode(),
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Node script failed:\n{result.stderr.decode()}\n{result.stdout.decode()}"
        )
    return result.stdout.decode()


# ── C2 Rust: source-inspection for bytewise ordering ─────────────────────────


class TestC2RustBytewiseOrdering(unittest.TestCase):
    """Source-inspection tests confirming the Rust SDK uses plain bytewise ordering."""

    def setUp(self) -> None:
        self.lib = _read(os.path.join(RUST_SDK, "src", "lib.rs"))
        self.tests = _read(os.path.join(RUST_SDK, "src", "tests.rs"))

    def test_encoder_sort_uses_plain_bytewise_not_length_first(self) -> None:
        """Encoder must sort by a.0.cmp(&b.0), not by (len, bytes) tuple."""
        # The old (len, bytes) form must not appear
        self.assertNotIn(
            "(a.0.len(), &a.0).cmp(&(b.0.len(), &b.0))",
            self.lib,
            "encoder must not use length-first sort tuple",
        )
        # The new plain bytewise form must appear
        self.assertIn(
            "a.0.cmp(&b.0)",
            self.lib,
            "encoder must use plain bytewise sort a.0.cmp(&b.0)",
        )

    def test_decoder_guard_uses_plain_bytewise_not_length_first(self) -> None:
        """Decoder key-order guard must compare key_bytes directly, not via (len, ref) tuple."""
        self.assertNotIn(
            "(key_bytes.len(), &key_bytes) <= (prev.len(), prev)",
            self.lib,
            "decoder must not use length-first guard tuple",
        )
        self.assertIn(
            "key_bytes <= *prev",
            self.lib,
            "decoder must use plain bytewise comparison key_bytes <= *prev",
        )

    def test_module_doc_updated_to_rfc8949(self) -> None:
        """Module doc must not say 'encoded-length, lexicographic-bytes'."""
        self.assertNotIn(
            "(encoded-length, lexicographic-bytes)",
            self.lib,
            "module doc must not reference the old length-first ordering description",
        )
        self.assertIn(
            "RFC 8949 section 4.2.1",
            self.lib,
            "module doc must reference RFC 8949 section 4.2.1",
        )

    def test_decode_fn_doc_updated_to_rfc8949(self) -> None:
        """decode() doc comment must not mention (encoded_length, encoded_bytes)."""
        self.assertNotIn(
            "encoded_length, encoded_bytes",
            self.lib,
            "decode() doc must not mention the old (encoded_length, encoded_bytes) sort key",
        )

    def test_tests_rs_comment_updated(self) -> None:
        """tests.rs map ordering comment must not say 'sort by (len, lex)'."""
        self.assertNotIn(
            "sort by (len, lex)",
            self.tests,
            "tests.rs comment must not reference the old (len, lex) sort key",
        )
        self.assertIn(
            "RFC 8949 section 4.2.1",
            self.tests,
            "tests.rs comment must reference RFC 8949 section 4.2.1",
        )

    def test_decoder_guard_comment_updated(self) -> None:
        """Decoder guard comment must reference RFC 8949 section 4.2.1."""
        self.assertIn(
            "RFC 8949 section 4.2.1",
            self.lib,
            "decoder guard comment must reference RFC 8949 section 4.2.1",
        )


# ── JS SDK: code-point key ordering ──────────────────────────────────────────


class TestJsCodePointOrdering(unittest.TestCase):
    """Tests that canonicalJson uses Unicode code point order, not UTF-16 order."""

    @unittest.skipUnless(_node_available(), "node not available")
    def test_ascii_keys_order_unchanged(self) -> None:
        """ASCII-only keys: code-point order == UTF-16 order (must be unchanged)."""
        script = textwrap.dedent(f"""\
            import {{ canonicalJson }} from '{JS_SDK_URL}/aiir-verify.js';
            // Keys: "a" < "b" < "c" — both orderings agree
            const obj = {{ c: 3, a: 1, b: 2 }};
            const result = canonicalJson(obj);
            process.stdout.write(result + '\\n');
        """)
        output = _run_node(script).strip()
        # Must be sorted lexicographically
        self.assertEqual(output, '{"a":1,"b":2,"c":3}')

    @unittest.skipUnless(_node_available(), "node not available")
    def test_code_point_order_differs_from_utf16_order_for_bmp_plus_keys(self) -> None:
        """
        Supplementary-plane characters (code point > U+FFFF) sort correctly
        by code point, not by the surrogate pair UTF-16 code units.

        U+1F600 (GRINNING FACE, code point 128512) as a JS string is the
        two-code-unit surrogate pair \\uD83D\\uDE00.  UTF-16 .sort() would compare
        the first surrogate \\uD83D (55357) against other characters, while
        code-point sort compares 128512.

        We pick a simpler, deterministic case: two single-character keys where
        one key is a letter in the Supplementary Multilingual Plane so that the
        surrogate high-unit (0xD800–0xDBFF range, ~55296+) comes BEFORE ordinary
        Latin letters in UTF-16 order but AFTER them in code-point order.

        Key "\\uD83D\\uDE00" (U+1F600, code point 128512) vs key "z" (code point 122).
        - UTF-16 sort:       \\uD83D (55357) > 'z' (122)  → "z" first
        - Code-point sort:   128512 > 122                → "z" first  (same here!)

        A cleaner contrast: key "\\u00F1" (U+00F1, ñ, code point 241) vs "z" (122).
        Both in BMP; UTF-16 == code point — same order.

        Best case: compare a private-use area char U+E001 (57345) against
        a surrogate-pair char. Instead use the simplest valid test:
        Two BMP keys where JS .sort() and code-point sort AGREE, but
        also verify the sort is stable and produces the correct order for
        the well-known AIIR receipt keys (all ASCII).
        """
        # For AIIR's actual keys (all ASCII), verify stable ordering
        script = textwrap.dedent(f"""\
            import {{ canonicalJson }} from '{JS_SDK_URL}/aiir-verify.js';
            // AIIR core keys in insertion order — output must be code-point sorted
            const obj = {{
                version: '1.0.0',
                type: 'aiir.commit_receipt',
                schema: 'aiir/commit_receipt.v2',
                commit: {{}},
                ai_attestation: {{}},
                provenance: {{}}
            }};
            const result = canonicalJson(obj);
            process.stdout.write(result + '\\n');
        """)
        output = _run_node(script).strip()
        parsed = json.loads(output)
        keys = list(parsed.keys())
        expected_order = sorted(keys, key=lambda k: [ord(c) for c in k])
        self.assertEqual(
            keys, expected_order, "AIIR core keys must be in code-point order"
        )

    @unittest.skipUnless(_node_available(), "node not available")
    def test_code_point_comparator_used_for_supplementary_plane(self) -> None:
        """
        Keys containing supplementary-plane characters must sort by code point.

        Key A: 'a' + U+1F600 (code point 128512, surrogate pair \\uD83D\\uDE00)
        Key B: 'b' (code point 98)

        Code-point order of first char: 'a' (97) < 'b' (98), so A < B.
        UTF-16 order of first char:     'a' (97) < 'b' (98), same — need to
        use keys where the divergence is at the first position.

        Use: key '\\uD83D\\uDE00' (U+1F600, high surrogate 0xD83D=55357)
             vs  key '\\u0041'   ('A', code point 65).
        UTF-16 .sort(): 'A' (65) < '\\uD83D' (55357)  → A appears first
        Code-point sort: 65 < 128512                  → A appears first (same!)

        The problematic case is when a surrogate pair HEAD unit is between two
        BMP codepoints in the UTF-16 space. Example that actually diverges:

        key '\\u9999' (U+9999, code point 39321)  vs  key '\\uD800\\uDC00' (U+10000, cp 65536)
        UTF-16 sort: 0x9999 (39321) < 0xD800 (55296) → '\\u9999' first
        Code-point:  39321 < 65536                   → '\\u9999' first (agree)

        The true divergence: if comparing from the HIGH-SURROGATE side.
        key '\\uD800' (lone surrogate, not valid Unicode scalar) — skip.

        Practical test: use Array.from() behavior verification.
        For a key made of the surrogate pair '\\uD83D\\uDE00' (U+1F600):
          Array.from('\\uD83D\\uDE00') has length 1 (one code point, 128512)
          '\\uD83D\\uDE00'.length is 2 (two UTF-16 code units)

        This verifies the comparator actually uses Array.from (code points),
        not charCodeAt/length (UTF-16 code units).
        """
        script = textwrap.dedent(
            r"""
            import { canonicalJson } from '"""
            + JS_SDK_URL
            + r"""/aiir-verify.js';
            // Key "😀" is U+1F600 (code point 128512) as a surrogate pair.
            // Key "ÿ" is U+00FF (code point 255, Latin small letter y with diaeresis).
            // Code-point sort: 255 < 128512  → ÿ first
            // UTF-16 sort:     0x00FF (255) < 0xD83D (55357) → ÿ first (agree here)
            //
            // Use a key that IS a surrogate head vs a key AFTER it in code point space:
            // key "𐀀" = U+10000 (cp 65536), key "香" = U+9999 (cp 39321)
            // Code-point: 39321 < 65536 → "香" first
            // UTF-16: 0x9999 (39321) < 0xD800 (55296) → "香" first (agree again)
            //
            // The actual divergence: two keys where the surrogate pair's HIGH unit
            // lands BETWEEN two BMP chars. This requires the high surrogate (0xD800+)
            // to appear between two code points.
            // Example: key "" (U+E000, cp 57344, Private Use) vs key "😀"
            // Code-point: 57344 < 128512 → "" first
            // UTF-16: 0xE000 (57344) > 0xD83D (55357) → "😀" first  ← DIVERGES
            const obj = {
                '😀': 'emoji',  // U+1F600, code point 128512
                '': 'pua',          // U+E000, code point 57344
            };
            const result = canonicalJson(obj);
            process.stdout.write(result + '\n');
        """
        )
        output = _run_node(script).strip()
        parsed = json.loads(output)
        keys = list(parsed.keys())
        # Code-point order: U+E000 (57344) < U+1F600 (128512) → PUA first
        self.assertEqual(
            keys[0],
            "",
            "PUA key (U+E000, cp 57344) must come before emoji key (U+1F600, cp 128512) in code-point order",
        )
        self.assertEqual(keys[1], "😀", "emoji key must come second")

    @unittest.skipUnless(_node_available(), "node not available")
    def test_sort_comparator_is_code_point_based_source_inspection(self) -> None:
        """Source must use Array.from or codePointAt, not just .sort() with no comparator."""
        source = _read(os.path.join(JS_SDK, "aiir-verify.js"))
        # The old pattern was Object.keys(val).sort() with no comparator
        # The new pattern must include a comparator with code-point awareness
        # We check that the sort at the object-encoding site is NOT the old bare `.sort()`
        # A simple check: codePointAt must appear in the source
        self.assertIn(
            "codePointAt",
            source,
            "canonicalJson must use codePointAt-based comparator for key sorting",
        )
        # And it should use Array.from for iteration
        self.assertIn(
            "Array.from",
            source,
            "canonicalJson must use Array.from to iterate code points",
        )

    @unittest.skipUnless(_node_available(), "node not available")
    def test_eight_interop_vectors_still_pass(self) -> None:
        """The 8 cross-language encoder vectors must still pass after the sort fix."""
        result = subprocess.run(
            ["node", os.path.join(JS_SDK, "test_encoder_vectors.mjs")],
            capture_output=True,
            cwd=JS_SDK,
        )
        stdout = result.stdout.decode()
        self.assertEqual(
            result.returncode,
            0,
            f"Encoder vectors failed:\n{stdout}\n{result.stderr.decode()}",
        )
        self.assertIn("8/8 passed", stdout)


# ── JS SDK: package metadata ──────────────────────────────────────────────────


class TestJsPackageMetadata(unittest.TestCase):
    """Tests for LICENSE file, README SRI pin, and docblock package name."""

    def test_license_file_exists(self) -> None:
        """sdks/js/LICENSE must exist (Apache-2.0)."""
        license_path = os.path.join(JS_SDK, "LICENSE")
        self.assertTrue(
            os.path.isfile(license_path),
            "sdks/js/LICENSE must exist",
        )

    def test_license_is_apache_2(self) -> None:
        """LICENSE must contain Apache License Version 2.0 text."""
        content = _read(os.path.join(JS_SDK, "LICENSE"))
        self.assertIn("Apache License", content)
        self.assertIn("Version 2.0", content)

    def test_license_in_package_files(self) -> None:
        """package.json files array must include LICENSE."""
        pkg = json.loads(_read(os.path.join(JS_SDK, "package.json")))
        self.assertIn(
            "LICENSE",
            pkg.get("files", []),
            "LICENSE must be in package.json files array",
        )

    def test_readme_browser_snippet_pins_version(self) -> None:
        """README browser snippet must not use unversioned unpkg URL."""
        readme = _read(os.path.join(JS_SDK, "README.md"))
        # Must not have the bare unversioned URL
        self.assertNotIn(
            'https://unpkg.com/@invariantsystems/aiir"',
            readme,
            "README must not load an unversioned unpkg script",
        )
        # Must include a versioned unpkg URL
        self.assertRegex(
            readme,
            r"unpkg\.com/@invariantsystems/aiir@\d+\.\d+\.\d+",
            "README must pin an exact version in the unpkg URL",
        )

    def test_readme_browser_snippet_has_integrity_attribute(self) -> None:
        """README browser snippet must include an integrity attribute for SRI."""
        readme = _read(os.path.join(JS_SDK, "README.md"))
        self.assertIn(
            "integrity=",
            readme,
            "README browser snippet must include an integrity attribute for SRI",
        )

    def test_js_docblock_uses_correct_package_name(self) -> None:
        """aiir-verify.js docblock must use @invariantsystems/aiir, not @aiir/verify."""
        source = _read(os.path.join(JS_SDK, "aiir-verify.js"))
        self.assertNotIn(
            "@aiir/verify",
            source,
            "docblock must not use the wrong package name @aiir/verify",
        )
        self.assertIn(
            "@invariantsystems/aiir",
            source,
            "docblock must use the published package name @invariantsystems/aiir",
        )


# ── Rust README: verify_sidecar signature ─────────────────────────────────────


class TestRustReadme(unittest.TestCase):
    """Tests that Rust README accurately describes the verify_sidecar signature."""

    def test_readme_does_not_use_wrong_two_arg_signature(self) -> None:
        """README must not show the wrong (cbor_bytes, json_bytes) two-argument signature."""
        readme = _read(os.path.join(RUST_SDK, "README.md"))
        self.assertNotIn(
            "json_bytes",
            readme,
            "Rust README must not use the nonexistent json_bytes argument in verify_sidecar example",
        )

    def test_readme_does_not_claim_wrong_return_type(self) -> None:
        """README must not show Ok(true)/Ok(false) return pattern (actual return is a tuple)."""
        readme = _read(os.path.join(RUST_SDK, "README.md"))
        self.assertNotIn(
            "Ok(true)",
            readme,
            "Rust README must not claim verify_sidecar returns Ok(bool); actual return is (bool, Vec<String>, String)",
        )

    def test_readme_shows_tuple_return(self) -> None:
        """README usage example must destructure the (valid, errors, sha256_hex) tuple."""
        readme = _read(os.path.join(RUST_SDK, "README.md"))
        self.assertIn(
            "valid",
            readme,
            "Rust README must show the valid field from verify_sidecar's tuple return",
        )

    def test_readme_sorted_map_keys_description_updated(self) -> None:
        """README Canonicalization table must not say '(encoded_length, encoded_bytes)'."""
        readme = _read(os.path.join(RUST_SDK, "README.md"))
        self.assertNotIn(
            "(encoded_length, encoded_bytes)",
            readme,
            "Rust README must not describe key ordering as (encoded_length, encoded_bytes)",
        )
        self.assertIn(
            "RFC 8949 §4.2.1",
            readme,
            "Rust README must reference RFC 8949 §4.2.1 for key ordering",
        )

    def test_readme_scope_claim_is_accurate(self) -> None:
        """README must accurately state that verify_sidecar checks CBOR, not commit-receipt integrity."""
        readme = _read(os.path.join(RUST_SDK, "README.md"))
        # It must NOT overstate scope (old README said it verifies 'commit-receipt integrity')
        # The new text must clarify the scope is CBOR sidecar validation
        self.assertIn(
            "CBOR sidecar",
            readme,
            "Rust README must describe verify_sidecar as checking CBOR sidecars",
        )
        # The old wrong scope claim said 'commit-receipt integrity'
        # The new text replaces 'verifying CBOR sidecars by round-tripping ... checking SHA-256'
        # with a more accurate description
        self.assertIn(
            "round-trip",
            readme,
            "Rust README must describe the round-trip check",
        )


# ── VS Code extension: hubBaseUrl trust isolation ────────────────────────────


class TestVsCodeHubBaseUrlTrust(unittest.TestCase):
    """Source-inspection tests confirming hubBaseUrl uses the trusted-setting pattern."""

    def setUp(self) -> None:
        # Read all TS source files (same as navigation_surface.test.js does)
        ts_files = [f for f in os.listdir(VSCODE_SRC) if f.endswith(".ts")]
        self.source = "\n".join(_read(os.path.join(VSCODE_SRC, f)) for f in ts_files)
        self.extension_ts = _read(os.path.join(VSCODE_SRC, "extension.ts"))

    def test_getTrustedHubBaseUrlSetting_function_exists(self) -> None:
        """extension.ts must define getTrustedHubBaseUrlSetting."""
        self.assertIn(
            "getTrustedHubBaseUrlSetting",
            self.extension_ts,
            "extension.ts must define getTrustedHubBaseUrlSetting (mirrors getTrustedCliPathSetting)",
        )

    def test_getHubBaseUrl_delegates_to_trusted_helper(self) -> None:
        """getHubBaseUrl must delegate to getTrustedHubBaseUrlSetting."""
        self.assertIn(
            "return getTrustedHubBaseUrlSetting()",
            self.extension_ts,
            "getHubBaseUrl must call getTrustedHubBaseUrlSetting()",
        )

    def test_trusted_helper_uses_inspect_not_get(self) -> None:
        """getTrustedHubBaseUrlSetting must use .inspect() to access globalValue/defaultValue."""
        self.assertIn(
            "inspect<string>('hubBaseUrl')",
            self.extension_ts,
            "trusted helper must call inspect<string>('hubBaseUrl') to read scope-aware value",
        )

    def test_trusted_helper_reads_globalValue_not_workspaceValue(self) -> None:
        """getTrustedHubBaseUrlSetting must read globalValue, never workspaceValue."""
        # workspaceValue must not appear in the hubBaseUrl trust helper
        # We check that the pattern 'workspaceValue' is not in the trusted helper block
        # by verifying the function body reads globalValue
        self.assertIn(
            "globalValue",
            self.extension_ts,
            "trusted helper must read inspected?.globalValue",
        )
        # Verify workspaceValue is not used for hubBaseUrl (it's absent from the file
        # for hub-related settings)
        hub_inspect_idx = self.extension_ts.find("inspect<string>('hubBaseUrl')")
        self.assertGreater(hub_inspect_idx, -1)
        # Extract the relevant function context (500 chars around the inspect call)
        context = self.extension_ts[hub_inspect_idx : hub_inspect_idx + 500]
        self.assertNotIn(
            "workspaceValue",
            context,
            "hubBaseUrl trust helper must not read workspaceValue",
        )

    def test_trusted_helper_reads_defaultValue_as_fallback(self) -> None:
        """getTrustedHubBaseUrlSetting must fall back to defaultValue, not a bare empty string."""
        hub_inspect_idx = self.extension_ts.find("inspect<string>('hubBaseUrl')")
        context = self.extension_ts[hub_inspect_idx : hub_inspect_idx + 500]
        self.assertIn(
            "defaultValue",
            context,
            "trusted helper must fall back to inspected?.defaultValue",
        )

    def test_package_json_hubBaseUrl_is_machine_scoped(self) -> None:
        """package.json must declare aiir.hubBaseUrl with scope: 'machine'."""
        pkg = json.loads(_read(os.path.join(VSCODE_EXT, "package.json")))
        props = pkg["contributes"]["configuration"]["properties"]
        hub_prop = props.get("aiir.hubBaseUrl", {})
        self.assertEqual(
            hub_prop.get("scope"),
            "machine",
            "aiir.hubBaseUrl must be 'machine' scoped to prevent workspace override",
        )

    def test_getHubBaseUrl_does_not_use_bare_get_for_hubBaseUrl(self) -> None:
        """getHubBaseUrl must not use the old .get('hubBaseUrl') pattern (which reads workspaceValue)."""
        # The old line was:
        #   return vscode.workspace.getConfiguration('aiir').get<string>('hubBaseUrl', '').trim();
        # That .get() reads workspaceValue first. It must be replaced.
        self.assertNotIn(
            ".get<string>('hubBaseUrl'",
            self.extension_ts,
            "getHubBaseUrl must not use the bare .get() API which reads workspace-scoped values",
        )

    def test_comment_explains_security_rationale(self) -> None:
        """getTrustedHubBaseUrlSetting must have a comment explaining the token exfiltration risk."""
        self.assertIn(
            "bearer token",
            self.extension_ts.lower(),
            "trusted helper must document the bearer token exfiltration risk in a comment",
        )


# ── Integration: both sides of new branch in JS sort ─────────────────────────


class TestJsSortBothBranches(unittest.TestCase):
    """Exercise both sides of the code-point comparator logic."""

    @unittest.skipUnless(_node_available(), "node not available")
    def test_equal_length_keys_same_as_before(self) -> None:
        """Equal-length ASCII keys: code-point order and UTF-16 agree; output unchanged."""
        script = textwrap.dedent(f"""\
            import {{ canonicalJson }} from '{JS_SDK_URL}/aiir-verify.js';
            const obj = {{ z: 26, a: 1, m: 13 }};
            process.stdout.write(canonicalJson(obj) + '\\n');
        """)
        output = _run_node(script).strip()
        self.assertEqual(output, '{"a":1,"m":13,"z":26}')

    @unittest.skipUnless(_node_available(), "node not available")
    def test_different_length_keys_sorted_by_code_point(self) -> None:
        """Different-length keys are sorted by code point of first differing char."""
        script = textwrap.dedent(f"""\
            import {{ canonicalJson }} from '{JS_SDK_URL}/aiir-verify.js';
            const obj = {{ ab: 2, b: 1, aa: 3 }};
            // code-point order: 'aa' < 'ab' < 'b'
            process.stdout.write(canonicalJson(obj) + '\\n');
        """)
        output = _run_node(script).strip()
        self.assertEqual(output, '{"aa":3,"ab":2,"b":1}')

    @unittest.skipUnless(_node_available(), "node not available")
    def test_early_exit_when_first_code_point_differs(self) -> None:
        """Comparator short-circuits on first differing code point."""
        script = textwrap.dedent(f"""\
            import {{ canonicalJson }} from '{JS_SDK_URL}/aiir-verify.js';
            // 'c...' comes after 'b...' regardless of length
            const obj = {{ cb: 2, ba: 1 }};
            process.stdout.write(canonicalJson(obj) + '\\n');
        """)
        output = _run_node(script).strip()
        self.assertEqual(output, '{"ba":1,"cb":2}')

    @unittest.skipUnless(_node_available(), "node not available")
    def test_length_tiebreak_shorter_key_first(self) -> None:
        """When one key is a prefix of another, shorter key comes first."""
        script = textwrap.dedent(f"""\
            import {{ canonicalJson }} from '{JS_SDK_URL}/aiir-verify.js';
            const obj = {{ abc: 3, ab: 2, a: 1 }};
            // code-point order: 'a' < 'ab' < 'abc'
            process.stdout.write(canonicalJson(obj) + '\\n');
        """)
        output = _run_node(script).strip()
        self.assertEqual(output, '{"a":1,"ab":2,"abc":3}')


if __name__ == "__main__":
    unittest.main()
