"""Repo-local public-surface drift checks.

These assertions intentionally stay filesystem-only so they can fail fast in CI
without needing the sibling website checkout.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


class TestPublicRepoSurfaceConsistency(unittest.TestCase):
    def _version(self) -> str:
        from aiir import __version__

        return __version__

    def _minor_series(self) -> str:
        major, minor, _patch = self._version().split(".")
        return f"{major}.{minor}.x"

    def test_release_health_tracks_current_release(self):
        content = _read("docs/reference/release-health.md")
        current = re.search(
            r"\*\*Current release\*\*:\s*v(?P<ver>\d+\.\d+\.\d+)",
            content,
        )
        self.assertIsNotNone(
            current, "Current release line missing from release-health"
        )
        self.assertEqual(current.group("ver"), self._version())

        history = re.search(r"^\| v(?P<ver>\d+\.\d+\.\d+) \|", content, re.MULTILINE)
        self.assertIsNotNone(
            history, "Release history table missing from release-health"
        )
        self.assertEqual(history.group("ver"), self._version())

    def test_citation_metadata_tracks_current_release(self):
        release_health = _read("docs/reference/release-health.md")
        history = re.search(
            r"^\| v(?P<ver>\d+\.\d+\.\d+) \| (?P<date>\d{4}-\d{2}-\d{2}) \|",
            release_health,
            re.MULTILINE,
        )
        self.assertIsNotNone(
            history, "Release history table missing current release date"
        )

        citation = _read("CITATION.cff")
        version = re.search(
            r"^version:\s*(?P<ver>\d+\.\d+\.\d+)$", citation, re.MULTILINE
        )
        date = re.search(
            r'^date-released:\s*"(?P<date>\d{4}-\d{2}-\d{2})"$',
            citation,
            re.MULTILINE,
        )
        self.assertIsNotNone(version, "CITATION.cff version missing")
        self.assertIsNotNone(date, "CITATION.cff date-released missing")
        self.assertEqual(version.group("ver"), self._version())
        self.assertEqual(date.group("date"), history.group("date"))

    def test_current_trust_claims_do_not_call_receipts_tamper_proof(self):
        self.assertNotIn("Tamper-**proof**", _read("SPEC.md"))
        self.assertNotIn("to tamper-proof", _read("THREAT_MODEL.md"))

    def test_public_repo_excludes_launch_and_outreach_strategy_docs(self):
        for rel_path in [
            "docs/launch/show-hn-draft.md",
            "docs/launch/show-hn-comment.txt",
            "docs/launch/launch-checklist.md",
            "docs/governance-adoption-plan.md",
            "docs/public-surface-audit-2026-06-04.md",
            "docs/drafts/aiir-self-dogfood-post.md",
            "docs/drafts/reddit-posts.md",
            "docs/drafts/show-hn.md",
            "docs/drafts/verifiable-ai-provenance-in-practice.md",
            "contrib/launch-post-devto.md",
            "contrib/launch-post-show-hn.md",
        ]:
            self.assertFalse(
                Path(rel_path).exists(), f"{rel_path} should not ship publicly"
            )

    def test_security_policies_track_current_minor_series(self):
        expected_series = self._minor_series()
        # The stale .github/SECURITY.md duplicate was removed (oss-hygiene audit
        # finding); the canonical root SECURITY.md is the single source of truth.
        for rel_path in ["SECURITY.md"]:
            content = _read(rel_path)
            active = re.search(
                r"^\| (?P<series>\d+\.\d+\.x)\s+\| ✅ Active \(current\) \|$",
                content,
                re.MULTILINE,
            )
            self.assertIsNotNone(active, f"Active release line missing from {rel_path}")
            self.assertEqual(active.group("series"), expected_series)

            upgrade = re.search(r"upgrade to (?P<series>\d+\.\d+\.x)", content)
            self.assertIsNotNone(upgrade, f"Upgrade target missing from {rel_path}")
            self.assertEqual(upgrade.group("series"), expected_series)

    def test_current_release_examples_track_package_version(self):
        expected = self._version()

        content = _read("SECURITY.md")
        verify_example = re.search(
            r"python scripts/verify-pypi-provenance\.py (?P<ver>\d+\.\d+\.\d+)",
            content,
        )
        self.assertIsNotNone(
            verify_example, "SECURITY.md versioned verifier example missing"
        )
        self.assertEqual(verify_example.group("ver"), expected)

        content = _read("docs/case-studies/aiir-self-dogfood.md")
        dogfood_example = re.search(
            r"python scripts/verify-release-evidence\.py (?P<ver>\d+\.\d+\.\d+)",
            content,
        )
        self.assertIsNotNone(
            dogfood_example, "Dogfood case-study release example missing"
        )
        self.assertEqual(dogfood_example.group("ver"), expected)

        wheel_versions = re.findall(
            r"aiir-(?P<ver>\d+\.\d+\.\d+)-py3-none-any\.whl",
            _read("docs/reference/verify-independently.md"),
        )
        self.assertGreater(
            len(wheel_versions), 0, "Offline verification wheel examples missing"
        )
        self.assertEqual(set(wheel_versions), {expected})

    def test_exact_public_test_counts_match_readme(self):
        # The collected-test count is intentionally NOT hardcoded in the headline
        # surfaces (README, CONTRIBUTING): it drifts on every PR — the oss-hygiene
        # audit finding about the stale "2,499 collected tests" claim. Both now
        # point to CI for the live count, and this guard prevents a hardcoded
        # count from being reintroduced.
        readme = _read("README.md")
        self.assertIn("100% test coverage (see CI for current count)", readme)
        self.assertNotRegex(readme, r"\d[\d,]* collected tests")

        contributing = _read("CONTRIBUTING.md")
        self.assertIn("see CI for current test count", contributing)
        self.assertNotRegex(contributing, r"\d[\d,]* collected tests")

        # docs/spec/standards-readiness.md is a dated scorecard snapshot; whatever
        # collected-test counts it cites must at least be internally consistent.
        standards = _read("docs/spec/standards-readiness.md")
        counts = set(re.findall(r"(\d[\d,]*) tests collected", standards))
        self.assertLessEqual(
            len(counts),
            1,
            f"Standards-readiness collected-test counts are inconsistent: {counts}",
        )
        self.assertNotIn("2214 collected tests", contributing)
        self.assertNotIn("2,214 collected tests", contributing)

    def test_standards_readiness_keeps_current_gap_closure_roadmap(self):
        scorecard = _read("docs/spec/standards-readiness.md")
        self.assertIn("## June/July Gap-Closure Roadmap", scorecard)
        self.assertNotIn("Month 3 (May 2026): Adoption proof", scorecard)

    def test_standards_readiness_does_not_reference_public_draft_repo_paths(self):
        scorecard = _read("docs/spec/standards-readiness.md")
        self.assertNotIn("docs/drafts/", scorecard)

    def test_standards_readiness_release_metric_matches_package_version(self):
        content = _read("docs/spec/standards-readiness.md")
        match = re.search(
            r"\| Release version \| `aiir --version` / PyPI \| [0-9-]+ \(v(?P<ver>\d+\.\d+\.\d+)\) \|",
            content,
        )
        self.assertIsNotNone(match, "Standards-readiness release metric missing")
        self.assertEqual(match.group("ver"), self._version())

    def test_standards_workflow_closes_superseded_weeklies(self):
        workflow = _read(".github/workflows/standards-readiness.yml")
        self.assertIn("Close superseded weekly issues", workflow)
        self.assertIn("gh issue close", workflow)
        self.assertIn("Superseded by the ${WEEK_LABEL}", workflow)

    def test_sync_workflow_enforces_gitlab_mirror_parity(self):
        workflow = _read(".github/workflows/sync.yml")
        self.assertNotIn("git push gitlab --all --force", workflow)
        self.assertIn("for branch in main receipts; do", workflow)
        self.assertIn("refs/remotes/origin/${branch}", workflow)
        self.assertIn("${ref}:refs/heads/${branch}", workflow)
        self.assertIn('if [ "$branch" = "main" ]; then', workflow)
        self.assertIn('git push gitlab "${ref}:refs/heads/${branch}"', workflow)
        self.assertIn('git push gitlab --force "${ref}:refs/heads/${branch}"', workflow)
        self.assertIn("main|receipts)", workflow)
        self.assertIn("Pruning non-canonical GitLab branches", workflow)
        self.assertIn("git push gitlab --delete", workflow)
        self.assertIn("git ls-remote --heads", workflow)
        self.assertIn("GitLab branch drift", workflow)

    def test_checked_in_aiir_ledger_snapshot_verifies(self):
        from aiir.cli import verify_receipt_ledger_file

        result = verify_receipt_ledger_file(str(REPO_ROOT / ".aiir/receipts.jsonl"))
        self.assertTrue(result["valid"], result.get("errors"))

        index = json.loads(_read(".aiir/index.json"))
        self.assertEqual(index["receipt_count"], result["count"])
        self.assertEqual(index["receipt_count"], result["valid_receipts"])
