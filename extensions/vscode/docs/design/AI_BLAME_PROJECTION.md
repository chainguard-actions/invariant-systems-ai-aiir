# AI Blame Projection

Developer design note for the AIIR VS Code extension.

This note defines the recommended design for AI blame in the AIIR VS Code
extension.

The goal is not to guess which lines were written by AI. The goal is to make
line annotations a deterministic projection of public AIIR evidence plus the
current repository snapshot.

## Problem

An AI blame surface is easy to make noisy and misleading.

The extension can already tell whether a commit has an active receipt and what
kind of evidence that receipt carries. What is still underspecified is how to
project that commit-level and file-level evidence onto the lines of an open
editor in a way that is:

- deterministic
- reviewable
- honest about ambiguity
- stable under refresh and navigation

Without a strict contract, users will treat a line marker as stronger proof than
the underlying receipt format can always support.

## Goals

- Produce the same annotations for the same repository snapshot and evidence set.
- Reuse one canonical active-receipt selection model across the extension.
- Distinguish strong file-scoped evidence from weaker commit-scoped evidence.
- Surface unknown and ambiguous cases explicitly.
- Keep the feature local-first and workspace-scoped.

## Non-Goals

- Prove who authored a line from first principles.
- Infer hidden AI usage from text style or heuristics beyond existing receipts.
- Reconstruct exact hunk-level authorship when receipts only carry commit-level
  evidence.
- Introduce network dependencies or remote verification for normal operation.

## Core Principle

AI blame should be implemented as a pure projection:

```text
projection(
  repository snapshot,
  active verified receipts,
  blame output,
  local policy mode
) -> line annotations
```

If the inputs do not change, the result must not change.

## Source Of Truth

AI blame should not parse `.aiir/receipts.jsonl` independently.

It should consume the extension's canonical active-receipt model:

- active receipt freshness selection per commit
- receipt validity state
- evidence tier
- per-file AI overlay derived from editor provenance and receipt file lists

This avoids two different definitions of "the current receipt for this commit"
living in the same extension.

## Evidence States

Every annotated line should be mapped to one of the following states.

### 1. `provable-file`

The line belongs to a commit whose active verified receipt contains explicit
editor provenance for the current file.

Meaning: file-scoped deterministic evidence exists.

### 2. `declared-file`

The line belongs to a commit whose active verified receipt explicitly covers the
current file through its file list, but without deterministic editor provenance.

Meaning: the file is in-scope for declared AI involvement, but the exact line is
still inferred from blame rather than proven by provenance spans.

### 3. `declared-commit`

The line belongs to a commit with valid AI involvement evidence, but the current
file is not explicitly covered or cannot be trusted as complete because the file
list was redacted or capped.

Meaning: the commit is AI-involved, but file coverage is ambiguous.

### 4. `bot-file`

The line belongs to a commit whose active verified receipt classifies the change
as bot-authored or AI+bot, and the file is explicitly covered.

### 5. `unknown-coverage`

The commit has a valid receipt, but the current file cannot be classified due to
redaction, capping, missing file list, or incompatible receipt structure.

### 6. `unattributed`

No active verified receipt supports an AI annotation for the line.

This state should usually render as no marker.

### 7. `pending-worktree`

The open editor contains staged, unstaged, or unsaved edits that are not yet
represented by git blame for the effective snapshot.

Meaning: the line is newer than the committed evidence.

## Default Policy

The recommended default is `strict`.

### Strict Mode

- Annotate only `provable-file`, `declared-file`, and `bot-file`.
- Render `declared-commit` and `unknown-coverage` as hover-only or muted
  warnings, not full blame markers.
- Treat absence of file coverage as unknown, not as human-authored.

### Permissive Mode

- Also annotate `declared-commit` lines.
- Use visibly weaker styling than file-scoped states.
- Tooltip must say that the line inherits commit-scoped evidence, not direct
  file-scoped proof.

## Snapshot Semantics

AI blame needs one explicit snapshot contract.

Recommended contract:

- If the editor is dirty, compute blame against the current buffer content.
- If the editor is clean, compute blame against the on-disk content.
- Tie every async result to the document URI plus document version.
- Discard stale results if the editor changed before blame finished.

This makes refresh behavior deterministic from the user's visible state instead
of from whichever shell command returned last.

## Blame Resolution Rules

For each visible line:

1. Resolve the effective file snapshot using the snapshot contract above.
2. Run git blame for that snapshot.
3. Resolve the blamed commit SHA.
4. Look up the active verified receipt for that commit.
5. Derive the strongest applicable evidence state for the current file.
6. Emit the corresponding annotation.

When multiple valid interpretations exist, prefer the most conservative one.

## Receipt Selection Rules

The projection must use the same active-record policy as the rest of the
extension.

- Multiple receipts for one commit: use the active freshest record.
- Invalid newer receipt beats stale valid assumptions if that is the canonical
  active record.
- Superseded receipts should not leak through to blame.
- Missing or malformed receipts produce no positive line attribution.

## File Coverage Rules

File coverage needs a stricter policy than commit coverage.

### Treat a file as explicitly covered only when one of these is true

- editor provenance explicitly references the current file
- receipt file list explicitly contains the current file path

### Treat file coverage as unknown when any of these is true

- `files_redacted` is present
- `files_capped` is present
- the receipt has AI involvement but no trustworthy file list
- the current file path cannot be matched after normalization

The feature must not silently upgrade unknown coverage into file-scoped proof.

## Rename And Copy Handling

This is a policy choice, not just an implementation detail.

Recommended initial behavior:

- support straightforward blame on the effective current path
- do not enable aggressive copy tracing by default
- optionally evaluate `git blame -M` for rename-aware movement inside the same
  file history

Rationale: aggressive blame tracing can make results harder to explain and more
expensive to compute. Conservative lineage is easier to defend publicly.

## Worktree Semantics

The feature should distinguish committed evidence from current uncommitted work.

- Unsaved buffer changes: mark affected lines as `pending-worktree`
- Saved but unstaged changes: same
- Staged but uncommitted changes: same
- New untracked files: no blame annotation, optional pending message

This prevents stale commit evidence from being painted onto lines that do not
yet belong to any commit.

## UI Guidance

The UI should encode evidence strength, not just AI presence.

Recommended hierarchy:

- `provable-file`: strongest visual treatment
- `declared-file`: medium treatment
- `bot-file`: distinct treatment
- `declared-commit`: muted treatment or hover-only
- `unknown-coverage`: warning treatment
- `pending-worktree`: neutral pending treatment

Tooltips should say exactly why a line is marked:

- "Deterministic editor provenance covers this file."
- "This file is explicitly covered by the active receipt."
- "This commit is AI-involved, but file-level coverage is ambiguous."
- "This line is newer than the last committed evidence."

## Testing Strategy

The current source-presence tests are not enough for this feature.

Add deterministic fixture tests for:

- active receipt freshness selection
- invalid vs valid receipt precedence
- file-scoped provenance mapping
- file list coverage mapping
- redacted file list behavior
- capped file list behavior
- commit-level fallback in permissive mode
- strict-mode suppression of ambiguous commit-only evidence
- stale async result cancellation by document version
- dirty editor vs clean editor snapshot behavior
- untracked file behavior
- rename behavior if supported

The core projection function should be testable without spinning up the whole
extension host.

## Recommended Refactor Shape

### Phase 1: Canonical projection core

- Extract a pure module, for example `ai_blame_projection.ts`
- Inputs:
  - active receipt lookup
  - file coverage resolver
  - blame lines
  - document metadata
  - policy mode
- Output:
  - deterministic per-line annotation states

### Phase 2: Thin editor adapter

- Keep `ai_blame_decorations.ts` focused on:
  - obtaining the effective snapshot
  - invoking blame
  - calling the projection core
  - translating states to decorations

### Phase 3: UX hardening

- add strict/permissive setting if needed
- add clear tooltips and legend text
- add pending-worktree behavior

## Future Extension

If AIIR later adds hunk-level or span-level provenance to receipts, the same
projection model can be upgraded without changing the public contract.

At that point, `provable-file` could split into stronger states such as:

- `provable-span`
- `provable-hunk`
- `provable-file`

Until then, the extension should avoid claiming more than the receipt format can
support.

## Recommended Decision

Adopt the following product stance now:

- one canonical active receipt model
- strict mode by default
- explicit unknown coverage state
- deterministic snapshot semantics
- real fixture tests before broadening UI claims

This is the most defensible path because it makes the feature predictable
without overstating what AIIR receipts prove.
