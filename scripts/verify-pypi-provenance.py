#!/usr/bin/env python3
"""
Verify PEP 740 attestations for AIIR releases via the PyPI Integrity API.

Queries PyPI's Integrity API endpoint to retrieve and display digital
attestations (SLSA provenance + PyPI Publish predicates) for every
wheel and source distribution in a given AIIR release.

VERIFICATION LEVELS
-------------------
This script operates at one of two levels depending on the installed extras:

  structural  (default, stdlib only)
      Checks that PyPI returns attestation bundles for each artifact and that
      the expected signer identity fields and predicate types are present in
      the bundle metadata.  It does NOT verify any cryptographic signature.
      A crafted or misattributed bundle would pass this check.

  cryptographic  (requires: pip install aiir[sign] or pip install sigstore
                             pypi-attestations)
      When the ``pypi_attestations`` and ``sigstore`` packages are importable,
      this script additionally performs real Sigstore bundle verification,
      enforces the expected signer identity (repository, workflow, environment),
      the publish/v1 predicate type, and checks that the bundle subject digest
      matches the artifact sha256.  A fabricated or misattributed bundle will
      fail this check.

Usage:
    # Verify the latest release
    python scripts/verify-pypi-provenance.py

    # Verify a specific version
    python scripts/verify-pypi-provenance.py 1.2.1

    # Strict mode -- exit 1 if any artifact lacks valid attestation
    python scripts/verify-pypi-provenance.py --strict

    # Show full attestation JSON
    python scripts/verify-pypi-provenance.py --verbose

Exit codes:
    0  All artifacts pass attestation checks
    1  Missing/invalid attestations in strict mode, or network/API error

Requires: Python 3.9+ (stdlib only for structural checks)

Copyright 2025-2026 Invariant Systems, Inc.
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

PYPI_PROJECT = "aiir"
PYPI_JSON_URL = "https://pypi.org/pypi/{project}/{version}/json"
PYPI_INTEGRITY_URL = (
    "https://pypi.org/integrity/{project}/{version}/{filename}/provenance"
)
PYPI_LATEST_URL = "https://pypi.org/pypi/{project}/json"

# Timeout for HTTP requests (seconds).
HTTP_TIMEOUT = 30

# Expected signer identity for AIIR releases (enforced at both levels).
EXPECTED_REPOSITORY = "invariant-systems-ai/aiir"
EXPECTED_WORKFLOW = "publish.yml"
EXPECTED_ENVIRONMENT = "pypi"
EXPECTED_PREDICATE_TYPE = "https://docs.pypi.org/attestations/publish/v1"

# Verification level labels.
LEVEL_STRUCTURAL = "structural"
LEVEL_CRYPTOGRAPHIC = "cryptographic"


def _crypto_libs_available() -> bool:
    """Return True when pypi_attestations + sigstore are importable."""
    try:
        importlib.import_module("pypi_attestations")
        importlib.import_module("sigstore")
        return True
    except ImportError:
        return False


def _fetch_json(url: str) -> Dict[str, Any]:
    """Fetch JSON from a URL.  Raises on HTTP or parse errors."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_json_safe(url: str) -> Tuple[Optional[Dict[str, Any]], int]:
    """Fetch JSON from a URL, returning (data, http_code).

    Returns (None, code) on HTTP errors instead of raising.
    """
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data, resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None, 0


def get_latest_version() -> str:
    """Fetch the latest version of the project from PyPI."""
    url = PYPI_LATEST_URL.format(project=PYPI_PROJECT)
    data = _fetch_json(url)
    return data["info"]["version"]


def get_release_files(version: str) -> List[Dict[str, Any]]:
    """Fetch the list of release files for a given version."""
    url = PYPI_JSON_URL.format(project=PYPI_PROJECT, version=version)
    data = _fetch_json(url)
    return data.get("urls", [])


def _check_bundle_structural(bundle: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Structurally validate a single attestation bundle dict.

    Checks that the bundle carries the expected publisher identity fields and
    the expected predicate type.  Does NOT verify any cryptographic signature.

    Returns (ok, list_of_issues).
    """
    issues: List[str] = []

    publisher = bundle.get("publisher")
    if not isinstance(publisher, dict):
        issues.append("bundle missing publisher object")
    else:
        repo = str(publisher.get("repository") or "")
        workflow = str(publisher.get("workflow") or "")
        env = str(publisher.get("environment") or "")
        if repo != EXPECTED_REPOSITORY:
            issues.append(
                "publisher.repository mismatch: got %r, expected %r"
                % (repo, EXPECTED_REPOSITORY)
            )
        if workflow != EXPECTED_WORKFLOW:
            issues.append(
                "publisher.workflow mismatch: got %r, expected %r"
                % (workflow, EXPECTED_WORKFLOW)
            )
        if env != EXPECTED_ENVIRONMENT:
            issues.append(
                "publisher.environment mismatch: got %r, expected %r"
                % (env, EXPECTED_ENVIRONMENT)
            )

    # Check predicate types inside nested attestations
    attestations = bundle.get("attestations", [])
    if not isinstance(attestations, list) or not attestations:
        issues.append("bundle has no attestations list")
    else:
        found_expected = False
        for att in attestations:
            if isinstance(att, dict):
                pt = str(att.get("predicate_type") or "")
                if pt == EXPECTED_PREDICATE_TYPE:
                    found_expected = True
        if not found_expected:
            issues.append(
                "expected predicate type %r not found in bundle"
                % EXPECTED_PREDICATE_TYPE
            )

    return (len(issues) == 0), issues


def _verify_bundles_crypto(
    bundles: List[Any],
    filename: str,
    artifact_sha256: str,
    version: str,
) -> Tuple[bool, List[str]]:
    """Perform real Sigstore/pypi-attestations cryptographic verification.

    Called only when pypi_attestations + sigstore are importable.
    Returns (all_ok, list_of_issues).
    """
    issues: List[str] = []
    try:
        import pypi_attestations as pa  # noqa: F401
    except ImportError as exc:
        issues.append("crypto libraries not importable: %s" % exc)
        return False, issues

    for bundle in bundles:
        if not isinstance(bundle, dict):
            continue
        for att in bundle.get("attestations", []):
            if not isinstance(att, dict):
                continue
            try:
                attestation = pa.Attestation.model_validate(att)
            except Exception as exc:
                issues.append(
                    "%s: failed to parse attestation object: %s" % (filename, exc)
                )
                return False, issues

            try:
                # verify() raises on failure, enforcing signer identity and
                # subject digest binding.
                attestation.verify(
                    pa.Publisher(
                        kind="GitHub",
                        repository=EXPECTED_REPOSITORY,
                        workflow=EXPECTED_WORKFLOW,
                        environment=EXPECTED_ENVIRONMENT,
                    ),
                    expected_digest=artifact_sha256 or None,
                )
            except Exception as exc:
                issues.append(
                    "%s: cryptographic verification failed: %s" % (filename, exc)
                )
                return False, issues

    return True, issues


def check_attestation(
    version: str,
    filename: str,
    artifact_sha256: str = "",
) -> Dict[str, Any]:
    """Query the PyPI Integrity API for attestations on a specific file.

    Returns a dict with:
      - filename: str
      - has_attestations: bool  (True only when signer-identity is valid AND
                                 cryptographic check succeeds when available)
      - http_code: int
      - attestation_count: int
      - predicates: list of predicate types found
      - verification_level: "structural" or "cryptographic"
      - structural_issues: list of identity/structure problems found
      - crypto_verified: bool (True only when cryptographic verification passed)
      - raw: full JSON response (if available)
    """
    url = PYPI_INTEGRITY_URL.format(
        project=PYPI_PROJECT, version=version, filename=filename
    )
    data, code = _fetch_json_safe(url)

    result: Dict[str, Any] = {
        "filename": filename,
        "has_attestations": False,
        "http_code": code,
        "attestation_count": 0,
        "predicates": [],
        "verification_level": LEVEL_STRUCTURAL,
        "structural_issues": [],
        "crypto_verified": False,
        "raw": data,
    }

    if data is None or code != 200:
        return result

    # PEP 740 response format: attestation_bundles or attestations array
    bundles = data.get("attestation_bundles", data.get("attestations", []))
    if not isinstance(bundles, list) or len(bundles) == 0:
        return result

    result["attestation_count"] = len(bundles)

    # Extract predicate types and run structural identity checks.
    predicates: List[str] = []
    all_structural_issues: List[str] = []
    all_bundles_ok = True

    for bundle in bundles:
        if isinstance(bundle, dict):
            # Direct attestation format
            pred_type = bundle.get("predicate_type", "")
            if pred_type:
                predicates.append(pred_type)
            # Bundle format with nested attestations
            for att in bundle.get("attestations", []):
                if isinstance(att, dict):
                    pt = att.get("predicate_type", "")
                    if pt:
                        predicates.append(pt)
            # Structural identity check -- signer must match EXPECTED_* constants.
            ok, issues = _check_bundle_structural(bundle)
            if not ok:
                all_bundles_ok = False
                all_structural_issues.extend(issues)

    result["predicates"] = predicates
    result["structural_issues"] = all_structural_issues

    # has_attestations is True only if structure + identity are valid.
    # A bundle from the wrong repo or with the wrong predicate type fails here.
    if not all_bundles_ok:
        result["has_attestations"] = False
        return result

    # Structural checks passed.
    result["has_attestations"] = True

    # Attempt cryptographic verification when libraries are available.
    if _crypto_libs_available():
        result["verification_level"] = LEVEL_CRYPTOGRAPHIC
        crypto_ok, crypto_issues = _verify_bundles_crypto(
            bundles, filename, artifact_sha256, version
        )
        if crypto_ok:
            result["crypto_verified"] = True
        else:
            # Cryptographic verification failed -- downgrade has_attestations.
            result["has_attestations"] = False
            result["structural_issues"].extend(crypto_issues)

    return result


def verify_release(
    version: str,
    *,
    strict: bool = False,
    verbose: bool = False,
) -> bool:
    """Verify PEP 740 attestations for all files in a release.

    Returns True if all files have valid attestations, False otherwise.

    When pypi_attestations + sigstore are available, verification is
    cryptographic (Sigstore bundle + signer identity + subject digest).
    Without those extras, verification is structural only (signer identity
    fields in the bundle metadata; no cryptographic signature is verified).
    """
    crypto_available = _crypto_libs_available()
    level_label = LEVEL_CRYPTOGRAPHIC if crypto_available else LEVEL_STRUCTURAL

    print("Verifying PEP 740 attestations for %s==%s" % (PYPI_PROJECT, version))
    print("PyPI: https://pypi.org/project/%s/%s/" % (PYPI_PROJECT, version))
    print("Verification level: %s" % level_label)
    if not crypto_available:
        print(
            "NOTE: pypi-attestations / sigstore not installed."
            " Checking attestation presence and signer-identity structure only."
            " Install aiir[sign] for cryptographic signature verification."
        )
    print()

    try:
        files = get_release_files(version)
    except Exception as e:
        print("ERROR: Could not fetch release info from PyPI: %s" % e, file=sys.stderr)
        return False

    if not files:
        print(
            "ERROR: No files found for %s==%s" % (PYPI_PROJECT, version),
            file=sys.stderr,
        )
        return False

    total = len(files)
    attested = 0
    results = []

    for file_info in files:
        filename = file_info["filename"]
        packagetype = file_info.get("packagetype", "unknown")
        size = file_info.get("size", 0)
        sha256 = str(file_info.get("digests", {}).get("sha256") or "")

        print("  %s" % filename)
        print("    Type: %s | Size: %s bytes" % (packagetype, "{:,}".format(size)))
        if sha256:
            print("    SHA-256: %s..." % sha256[:16])

        result = check_attestation(version, filename, artifact_sha256=sha256)
        results.append(result)

        if result["has_attestations"]:
            attested += 1
            count = result["attestation_count"]
            vlevel = result["verification_level"]
            print("    Attestations: %d found (%s check passed)" % (count, vlevel))
            if result.get("crypto_verified"):
                print("    Cryptographic verification: PASSED")
            elif vlevel == LEVEL_STRUCTURAL:
                print(
                    "    Cryptographic verification: NOT PERFORMED"
                    " (structural check only)"
                )
            if result["predicates"]:
                for pred in result["predicates"]:
                    print("      - %s" % pred)
            else:
                print("      (predicate types not enumerated in response)")
        else:
            if result["structural_issues"]:
                for issue in result["structural_issues"]:
                    print("    ISSUE: %s" % issue)
            if result["http_code"] == 404:
                print("    Attestations: none (Integrity API returned 404)")
            elif result["http_code"] == 0:
                print("    Attestations: could not reach Integrity API")
            elif result["structural_issues"]:
                print("    Attestations: present but failed validation checks")
            else:
                print("    Attestations: none (HTTP %d)" % result["http_code"])

        if verbose and result["raw"]:
            print("    Raw response:")
            print("      %s" % json.dumps(result["raw"], indent=2)[:500])

        print()

    # Summary
    print("=" * 60)
    print("Summary: %d/%d artifacts passed attestation checks" % (attested, total))
    print("Verification level: %s" % level_label)
    print()

    if attested == total and total > 0:
        if crypto_available:
            print(
                "All release artifacts passed cryptographic attestation verification."
            )
            print(
                "Supply chain: OIDC identity (Trusted Publishing)"
                " -> Sigstore signature -> PyPI attestation"
            )
        else:
            print(
                "All release artifacts have attestation bundles"
                " with expected signer-identity structure."
            )
            print(
                "NOTE: This is a structural check only -- attestation presence"
                " and publisher identity fields were validated, but NO"
                " cryptographic signature was verified."
            )
            print("Install aiir[sign] and re-run for cryptographic verification.")
        return True
    elif attested > 0:
        print("Partial coverage: %d/%d passed attestation checks." % (attested, total))
        if not strict:
            print("Run with --strict to fail on incomplete attestation coverage.")
        return not strict
    else:
        print("No valid attestations found.")
        print()
        print("This may indicate:")
        print("  - The release was published before PEP 740 support was enabled")
        print("  - Attestations are still propagating (try again in a few minutes)")
        print("  - The release was not published via Trusted Publishing (OIDC)")
        print("  - Attestation bundles are present but failed signer-identity checks")
        return not strict


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check PEP 740 attestation presence and signer-identity structure for"
            " AIIR releases on PyPI. When pypi-attestations + sigstore are"
            " installed, also performs cryptographic Sigstore bundle verification."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s              # verify latest release\n"
            "  %(prog)s 1.2.1        # verify specific version\n"
            "  %(prog)s --strict     # exit 1 if any artifact lacks valid attestations\n"
            "  %(prog)s --verbose    # show raw attestation JSON\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="Version to verify (default: latest on PyPI)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any artifact lacks valid attestations",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full attestation JSON responses",
    )
    args = parser.parse_args()

    version = args.version
    if version is None:
        try:
            version = get_latest_version()
            print("Latest version on PyPI: %s" % version)
            print()
        except Exception as e:
            print("ERROR: Could not fetch latest version: %s" % e, file=sys.stderr)
            sys.exit(1)

    ok = verify_release(version, strict=args.strict, verbose=args.verbose)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
