# GitLens Commit Composer + AIIR Receipts

Use GitLens to compose AI-assisted commits quickly, then use AIIR to make those commits auditable.

## Positioning

- **GitLens**: commit composition and commit UX.
- **AIIR**: receipt generation, verification, and policy enforcement.

This keeps responsibilities clear:

> GitLens writes the commit story. AIIR proves the story happened.

## Why this integration matters

GitLens now exposes AI-assisted commit workflows (including MCP tooling). AIIR should treat that as an upstream activity source and generate a verifiable receipt immediately afterward.

Recommended operator rule:

```text
After any GitLens commit composition action, generate an AIIR receipt for the resulting commit (or branch range).
Do not describe a GitLens-composed commit as verified unless the AIIR receipt verifies.
```

## Evidence model for GitLens-assisted commits

AIIR should not overclaim hidden AI usage. Prefer explicit evidence tiers:

| Evidence tier | Meaning |
|---|---|
| `declared` | User/agent/trailer/workflow explicitly declared AI assistance. |
| `ide-context` | GitLens extension context was observed in-editor when receipt was generated. |
| `mcp-observed` | Agent workflow invoked a GitLens MCP action and then AIIR receipt generation. |
| `deterministic-provenance` | AIIR captured deterministic editor/file provenance signals. |
| `signed-ci` | Receipt was generated in CI and cryptographically signed/verified. |

Current implementation rule:

```text
Record GitLens as companion tool context when the extension is present and active.
Do not treat GitLens presence alone as AI authorship; reserve AI trailers for declared or attested AI participation.
```

Example tool context:

```json
{
  "tool_context": [
    {
      "tool": "GitLens",
      "extension_id": "eamodio.gitlens",
      "feature": "companion_extension",
      "evidence_level": "ide-context",
      "evidence": [
        "gitlens_extension_present",
        "gitlens_extension_active"
      ]
    }
  ]
}
```

## Recommended near-term implementation order

1. **Docs/positioning**: publish this workflow as “GitLens composition + AIIR provenance”.
2. **Soft extension detection**: detect `eamodio.gitlens` in VS Code without hard dependency.
3. **MCP workflow rule**: codify “GitLens compose → AIIR receipt” in
  `mcp-manifest.json` as `gitlens_commit_composer_receipt`.
4. **Receipt trailers**: support discoverable trailers such as:

    - `AI-Assisted-By: GitLens Commit Composer`
    - `AIIR-Receipt: .aiir/receipts.jsonl#<receipt-id>`
    - `AIIR-Evidence-Level: declared+ide-context`

5. **CI policy template**: require verifiable receipts when AI assistance is declared.

## MCP workflow rule

AIIR publishes a first-class MCP workflow rule named
`gitlens_commit_composer_receipt`. It does not add a separate tool; it chains the
existing `aiir_receipt` tool after an explicit GitLens Commit Composer or
GitLens MCP commit-composition action.

The workflow rule carries the same tool-context payload the VS Code extension
can already attach to receipts:

```json
{
  "tool": "GitLens",
  "extension_id": "eamodio.gitlens",
  "feature": "commit_composer",
  "evidence_level": "ide-context",
  "evidence": ["gitlens_commit_composer"]
}
```

Plain GitLens extension presence still records only companion context. The
Commit Composer feature marker is the boundary that lets AIIR emit authoring
trailers.

## Trailer behavior

When a receipt contains explicit GitLens Commit Composer context, `aiir --trailer`
emits discoverable trailers:

```text
AIIR-Receipt: .aiir/receipts.jsonl#g1-...
AIIR-Type: aiir.commit_receipt
AIIR-AI: true
AI-Assisted-By: GitLens Commit Composer
AIIR-Evidence-Level: declared+ide-context
AIIR-Verified: true
```

When the GitLens extension is merely present and active, AIIR can record
`extensions.tool_context`, but the trailer remains non-authoring:

```text
AIIR-AI: false
AIIR-Verified: true
```

## Partnership guidance

Yes, reach out to GitKraken/GitLens — **after** AIIR ships a minimal integration path. Ask for small, low-friction collaboration first (events/hooks, external actions surface, or companion-documentation mention).

That sequencing avoids platform dependency risk while making AIIR the neutral accountability layer across AI coding tools.
