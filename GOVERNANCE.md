# Governance

## Maintainership

AIIR is maintained by **Invariant Systems, Inc.**, with a single primary
maintainer (Noah, [noah@invariantsystems.io](mailto:noah@invariantsystems.io)).

> **Bus-factor disclosure**: This project currently has a bus factor of 1.
> The single maintainer is responsible for releases, security fixes, and
> specification governance. This is a known operational risk. Future plans
> include expanding the maintainer set as the project grows.

## Decision-making

Specification and codebase decisions are made by the maintainer, informed by:

- GitHub Issues and Discussions (public input)
- Security disclosures (private input, see [SECURITY.md](SECURITY.md))
- Empirical evidence from the deployed dogfood ledger

Large or breaking changes follow the SPEC_GOVERNANCE.md Stage-gate process
(see [SPEC_GOVERNANCE.md](SPEC_GOVERNANCE.md)).

## Release authority

Only repository admins can create releases. Releases require:

1. Green CI on `main` (all four merge gates)
2. Version bump propagated via `python scripts/sync-version.py --fix`
3. Tagged commit published to PyPI via the Publish workflow

## Security response

Security response SLAs are documented in [SECURITY.md](SECURITY.md).

> **Reconciliation with solo-maintainer reality**: The SLAs in SECURITY.md
> (24-hour acknowledgment, 7-day fix for Critical/High) represent genuine
> targets but depend on a single person. If a Critical vulnerability is
> reported while the maintainer is unavailable, response may be delayed.

## Contribution process

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide,
including DCO requirements, merge gates, and the PR review process.

## Trademark

"AIIR", "AI Integrity Receipts", and "Invariant Systems" are trademarks of
Invariant Systems, Inc. See [TRADEMARK.md](TRADEMARK.md) for usage guidelines.

## License

Apache-2.0. See [LICENSE](LICENSE).
