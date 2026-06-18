# AIIR Documentation

AIIR (AI Integrity Receipts) produces tamper-evident receipts that record who or
what produced a code change. This index maps the docs from the shortest possible
path to deep reference material. New here? Start with the
[project front door](../README.md), then follow the
[solo-developer guide](guides/guide-solo-developer.md) to get your first receipt
in five minutes. If you have received a receipt and want to check it yourself,
jump to [verify independently](reference/verify-independently.md). Like the tool,
these docs are openly AI-assisted.

## Start here

- [Project front door](../README.md) — what AIIR is, status, and the fastest way in.
- [Solo-developer guide](guides/guide-solo-developer.md) — first receipt in under 5 minutes.
- [Verify independently](reference/verify-independently.md) — check a receipt without trusting AIIR.
- [CLI reference](reference/cli.md) — every command, flag, and exit code in one place.
- [CI platforms](integrations/ci-platforms.md) — wire AIIR into GitHub Actions, GitLab, and more.

## Guides

- [Solo developer](guides/guide-solo-developer.md) — adopt AIIR alone or on a small team.
- [OSS maintainer](guides/guide-oss-maintainer.md) — signed receipts in CI, PR policy gate, release attestation.
- [Security team](guides/guide-security-team.md) — evaluate trust properties and integrate into audit workflows.
- [Claude Code hooks](guides/claude-code-hooks.md) — auto-emit a receipt every time Claude Code commits.
- [Release evidence bundles](guides/release-bundles.md) — package a release-scoped decision, receipts, and auditor report.

## Integrations

- [CI platforms](integrations/ci-platforms.md) — wire AIIR into your CI/CD pipelines.
- [GitLab provenance evidence](integrations/gitlab-provenance-evidence.md) — emit a structured provenance artifact from GitLab CI.
- [GitLab Duo recipe](integrations/gitlab-duo-recipe.md) — receipt and audit Duo-generated merge requests.
- [GitLab webhooks](integrations/gitlab-webhooks.md) — server-side receipt generation without a CI pipeline.
- [GitLab Pages dashboard](integrations/gitlab-pages-dashboard.md) — static dashboard of AI authorship trends and receipt history.
- [GitLab compliance framework](integrations/gitlab-compliance-framework.md) — enforce receipt generation across a whole group.
- [GitLens integration](integrations/gitlens-integration.md) — compose AI-assisted commits in GitLens, make them auditable with AIIR.
- [Agent-receipt contract](integrations/agent-receipt-contract.md) — draft profile for portable agent-assisted-work receipts.
- [Agent trace interoperability](integrations/agent-trace-interoperability.md) — how AIIR and Agent Trace occupy complementary layers.
- [Ecosystem](integrations/ecosystem.md) — where AIIR fits in the supply-chain security stack.

## Reference

- [CLI](reference/cli.md) — full command, flag, and exit-code reference.
- [CLI subcommands](reference/cli-subcommands.md) — the subcommand form alongside the canonical flat flags.
- [Python API](reference/api.md) — the zero-dependency `aiir` module surface.
- [MCP server](reference/mcp.md) — run AIIR as MCP tools; client config for Claude Desktop, Cursor, Continue, and more.
- [SDKs](reference/sdks.md) — the reference implementation and language SDKs.
- [Tamper detection](reference/tamper-detection.md) — how content addressing protects receipt integrity.
- [Commitment receipts](reference/commitment-receipts.md) — receipts for artifacts beyond git commits.
- [Implementers and pilots](reference/implementers.md) — public registry of known AIIR implementations.
- [Operator model](reference/operator-model.md) — the shortest human-facing model of what AIIR does.
- [Testing](reference/testing.md) — local test tiers and how they map to CI.
- [Release health](reference/release-health.md) — current release, channels, and status badges.
- [Trap-case catalog](reference/trap-case-catalog.md) — what green-but-ambiguous results mean for real decisions.
- [Automation secrets](reference/automation-secrets.md) — where long-lived automation credentials live and how they are delivered.
- [Research-evidence receipts](reference/research-evidence-receipts.md) — draft profile for governed research claims and evidence.
- [Compliance mapping](reference/compliance-mapping.md) — starter mapping from receipts to key compliance frameworks.

## Specification & governance

- [Specification](../SPEC.md) — the AIIR commit-receipt format (Spec v2.0.0, stable).
- [Spec governance](../SPEC_GOVERNANCE.md) — how the receipt format is maintained, versioned, and extended.
- [Threat model](../THREAT_MODEL.md) — STRIDE-per-element analysis with DREAD scoring and attack trees.
- [Security policy](../SECURITY.md) — supported versions and how to report vulnerabilities.
- [Privacy](../PRIVACY.md) — what personal data receipts contain and the controls available.
- [Architecture](../ARCHITECTURE.md) — the reference implementation's components and data flow.
- [Standards-readiness scorecard](spec/standards-readiness.md) — weekly readiness scoring on the public standards track.
- [Stability contract](spec/stability-contract.md) — the guarantees that take effect at 1.0 (draft).
- [Residual risk boundary](spec/residual-risk.md) — what AIIR decides reliably and what it deliberately does not.
- [IETF draft](ietf/draft-invariantsystems-aiir-receipt-00.md) — the commit-receipt format as an Internet-Draft.

## Case studies

- [AIIR self-dogfood](case-studies/aiir-self-dogfood.md) — how the AIIR project uses its own receipts on itself.
- [NISQ research evidence](case-studies/nisq-research-evidence.md) — the research-evidence profile applied to a NISQ readiness capsule.

## Project

- [Contributing](../CONTRIBUTING.md) — how to set up, build, and submit changes.
- [Governance](../GOVERNANCE.md) — maintainership and decision-making.
- [Support](../SUPPORT.md) — where to get help.
- [Code of conduct](../CODE_OF_CONDUCT.md) — community standards (Contributor Covenant).
- [Changelog](../CHANGELOG.md) — notable changes across releases.
- [Trademark policy](../TRADEMARK.md) — AIIR marks and acceptable open-source use.
