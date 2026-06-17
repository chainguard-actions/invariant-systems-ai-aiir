# AIIR → GUAC Integration

Feed AIIR receipts into [GUAC](https://guac.sh) so your software supply-chain
graph can answer: **"Which packages in my dependency tree have commits with
declared AI authorship, and do those commits carry valid receipts?"**

## How it works

AIIR receipts are already compatible with GUAC's ingestion pipeline
because AIIR natively emits [in-toto Statement v1](https://in-toto.io/Statement/v1)
envelopes via `--in-toto`. GUAC ingests in-toto statements and maps them
to its graph ontology.

The AIIR predicate type is:

```text
https://invariantsystems.io/predicates/aiir/commit_receipt/v2
```

```text
git commit
    │
    ▼
aiir --in-toto --sign     ← generates in-toto Statement v1 + Sigstore signature
    │
    ▼
attestation.intoto.jsonl   ← standard DSSE envelope (if signed) or bare statement
    │
    ▼
guacone collect files ./   ← GUAC collector ingests the attestation
    │
    ▼
GUAC graph                 ← queryable: "which artifacts have AI-authored sources?"
```

## Quick start

### 1. Generate receipts as in-toto statements

```bash
# Receipt a commit and wrap in in-toto Statement v1
aiir --in-toto --pretty

# Receipt + sign (Sigstore OIDC)
aiir --in-toto --sign

# Receipt a range of commits (e.g., a release branch)
aiir --in-toto --range v1.2.5..v1.3.0 --output-dir .aiir/attestations/
```

Each receipt becomes an in-toto Statement with:

- **subject**: `<repo>@<commit_sha>` with `digest.gitCommit`
- **predicateType**: `https://invariantsystems.io/predicates/aiir/commit_receipt/v2`
- **predicate**: the full AIIR receipt (commit metadata, AI signals, content hash)

### 2. Ingest into GUAC

```bash
# Ingest all AIIR attestations into a running GUAC instance
guacone collect files .aiir/attestations/

# Or pipe directly
aiir --in-toto --json | guacone collect files /dev/stdin
```

### 3. Query the graph

Once ingested, GUAC maps AIIR attestations to `HasMetadata` nodes
linked to the source artifact (git commit). You can query:

```graphql
# Find all artifacts with AIIR attestations
{
  HasMetadata(hasMetadataSpec: {
    key: "aiir:predicateType"
    value: "https://invariantsystems.io/predicates/aiir/commit_receipt/v2"
  }) {
    subject {
      ... on Source {
        type
        namespaces {
          namespace
          names {
            name
            tag
            commit
          }
        }
      }
    }
    key
    value
    timestamp
    collector
  }
}
```

### 4. Policy queries

Combine AIIR metadata with GUAC's other data to build policies:

```graphql
# Find packages whose source commits are AI-authored but unsigned
{
  HasMetadata(hasMetadataSpec: {
    key: "aiir:ai_classified"
    value: "true"
  }) {
    subject {
      ... on Source {
        namespaces {
          names { name commit }
        }
      }
    }
    # Cross-reference with CertifyGood for signing status
  }
}
```

## What GUAC gains

| Without AIIR | With AIIR |
|---|---|
| GUAC knows *what* was built and *how* (SLSA build provenance) | GUAC also knows *what produced the source change* (human, AI-assisted, bot) |
| Vulnerability scanning covers known CVEs | AI-authored code paths are identifiable for targeted review |
| Dependency graph shows transitive risk | AI authorship metadata propagates through the graph |

## Predicate schema

The AIIR predicate contains:

```json
{
  "type": "aiir/commit_receipt",
  "schema": "https://invariantsystems.io/schemas/aiir/commit_receipt.v2.json",
  "version": "2.0.0",
  "commit": {
    "sha": "c4dec85630...",
    "author": { "name": "...", "email": "..." },
    "committer": { "name": "...", "email": "..." },
    "message_hash": "sha256:...",
    "diff_hash": "sha256:...",
    "tree_hash": "..."
  },
  "ai_attestation": {
    "declared": true,
    "classification": "ai_assisted",
    "signals_detected": ["copilot"],
    "detection_method": "trailer_and_heuristic"
  },
  "provenance": {
    "generator": "aiir",
    "generator_version": "1.3.0",
    "repository": "https://github.com/org/repo",
    "timestamp": "2026-03-31T12:00:00Z"
  }
}
```

Full schema: [`schemas/commit_receipt.v2.schema.json`](../../schemas/commit_receipt.v2.schema.json)

## Files in this directory

| File | Purpose |
|---|---|
| `aiir_to_guac.py` | Batch converter: AIIR ledger → in-toto statements for GUAC ingestion |
| `example_queries.graphql` | Ready-to-use GUAC GraphQL queries for AI authorship metadata |

## References

- [AIIR Specification](../../SPEC.md)
- [GUAC Documentation](https://docs.guac.sh)
- [in-toto Attestation Spec](https://github.com/in-toto/attestation/tree/main/spec/v1)
- [AIIR in-toto integration](../../ARCHITECTURE.md#integration-recipes)
