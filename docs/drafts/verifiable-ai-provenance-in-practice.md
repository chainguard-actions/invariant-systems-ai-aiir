# Verifiable AI Provenance in Practice

AI-assisted software development has moved faster than the evidence layer around
it.

Teams use Copilot, Claude, ChatGPT, Cursor, GitLab Duo, GitLens Commit Composer,
and other tools in everyday engineering work. The output lands in git. Six
months later, someone asks a reasonable question: which commits involved AI, and
can you prove the answer without trusting a dashboard screenshot or a policy
document?

Git alone does not answer that question. Commit trailers help when people add
them, but they are free text. CI logs help until retention windows expire.
Vendor-specific activity data helps inside a platform boundary, but source code
outlives platforms, workflows, and tool contracts.

AIIR is the missing receipt layer for that moment.

## What AIIR does

AIIR generates deterministic, content-addressed receipts for git commits with
declared AI involvement. A receipt records commit metadata, AI-authorship
signals, provenance, and a SHA-256 content hash over a canonical core object.

Run it locally:

```bash
pip install aiir
aiir --pretty
aiir --verify .aiir/receipts.jsonl
```

The result is a plain JSON receipt that can be verified anywhere. Change a core
field and verification fails. Generate the receipt again from the same commit
core and the content hash is the same.

That is the point: no hosted service is required for basic verification.

## The wedge: declared provenance

AIIR does not claim to detect hidden AI usage. That boundary is intentional.

The reliable first step is declared provenance: commit trailers, bot identity,
agent context, CI generator identity, MCP transport context, and editor workflow
metadata that tools intentionally expose. AIIR turns those signals into a
portable receipt instead of leaving them as scattered text.

That means AIIR is useful even before every editor and assistant emits perfect
provenance. It gives teams a stable place to put the evidence they do have, and
it gives tool vendors a simple target to integrate with.

## How it fits the supply chain

AIIR works before build provenance.

SLSA can explain how an artifact was built. Sigstore can explain who signed an
artifact. in-toto can link supply-chain steps. GUAC can query graph evidence.
Witness can collect attestations during a run.

AIIR answers a different question: what produced the source change?

That authorship-level claim can then flow into the rest of the stack:

- `--in-toto` wraps receipts as in-toto Statement v1 predicates.
- Sigstore signing binds full receipts, including extensions.
- GUAC can ingest AIIR predicates and make AI-authored source paths queryable.
- Witness can capture AIIR receipts as attestation products.
- AMPEL-style policy engines can evaluate receipt facts.

## Why this matters now

Security and compliance teams are starting to ask for AI traceability in code
review, change management, and release evidence. The wrong answer is a private
spreadsheet. The brittle answer is grepping commit messages. The durable answer
is a receipt format that survives outside any one tool.

AIIR is deliberately small:

- Apache-2.0
- Python 3.9+
- zero runtime dependencies
- public JSON schema and CDDL grammar
- published conformance vectors
- Python reference implementation and TypeScript verifier
- GitHub Action, GitLab CI/CD Catalog component, VS Code extension, and MCP
  server surfaces

The project also receipts itself. Its own public repository carries dogfood
receipts, release evidence, conformance tests, and a threat model so reviewers
can inspect the claims rather than trust a launch page.

## The invitation

AIIR is not asking the ecosystem to adopt a hosted control plane. It is asking
for review of a portable evidence shape.

Good next steps for different readers:

- If you maintain an OSS project, add the GitHub Action or GitLab Catalog
  component and receipt a few AI-assisted commits.
- If you build developer tools, emit declared AI context that AIIR can preserve
  in receipts.
- If you work on supply-chain security, review the schema, CDDL grammar, and
  IETF draft artifacts.
- If you run compliance or security review, try verifying receipts locally and
  decide which policy thresholds matter for your organization.

The core idea is simple: AI involvement in source changes should be portable,
verifiable, and reviewable after the moment of coding has passed.

That is what AIIR receipts are for.
