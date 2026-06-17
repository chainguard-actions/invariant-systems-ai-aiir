# AIIR Receipts AIIR

AIIR asks teams to keep verifiable records of declared AI involvement in git
commits. The project uses that same workflow on itself.

That is the simplest adoption test available to an open-source provenance tool:
does it survive contact with its own development loop?

## What is dogfooded

The AIIR repository uses the public receipt surfaces it ships for everyone else:

- local CLI receipt generation and verification
- GitHub Action receipts in CI
- GitLab CI/CD Catalog receipts on the GitLab side
- MCP receipt generation and verification from assistant-driven workflows
- release evidence checks for published artifacts

There is no private verifier and no internal-only receipt format. The same JSON
receipt shape, content hash, and verification algorithm are used by downstream
users.

## What the public artifacts show

The repository exposes the materials a reviewer can check without asking for a
demo account:

- `.receipts/` and `.aiir/` evidence in the repo history
- the README proof table
- conformance vectors for independent implementers
- a TypeScript verifier written against the public specification
- GitHub/GitLab CI integration examples
- release evidence verification scripts
- a published threat model

That does not make AIIR "adopted" by the market. It does make the internal
claim testable: AIIR can generate and verify its own evidence through the same
interfaces it asks others to use.

## What dogfooding revealed

The most important lesson is that declared provenance is the right first wedge.

Many real AI-assisted workflows still do not emit durable authorship signals.
Chat-based assistants can shape a change without leaving a commit trailer. Some
editor tools provide context only while the editor is active. Commit messages
can be rewritten.

AIIR does not paper over that gap. It records declared and observable signals,
then distinguishes them by evidence level. For example, GitLens extension
presence is companion context only, while an explicit GitLens Commit Composer
action can emit authoring trailers and evidence levels.

That distinction matters because a provenance tool loses trust when it
overclaims.

## Why zero dependencies matters

Receipt verification should not require a service account, a network call, or a
large dependency graph. AIIR's core verifier remains standard-library-only so a
maintainer, auditor, or CI runner can verify receipts with minimal setup.

Signing and ecosystem wrappers are still available when needed. Sigstore can
bind the full receipt to an identity. in-toto can carry the receipt as a
predicate. GUAC and Witness can consume the evidence in broader supply-chain
flows. But the local receipt remains useful on its own.

## What remains

Dogfooding is not the same as third-party adoption. The next milestone is public
use outside the AIIR repository: external OSS pilots, independent review of the
IETF draft, and partner workflows around GitLab, GitLens, GUAC, Witness, and
AMPEL policy evaluation.

The internal foundation is now close enough to support that push: receipts,
verification, CI surfaces, ecosystem adapters, and standards artifacts all have
public review paths.

The next job is not more private polish. It is getting outside eyes on the
format.
