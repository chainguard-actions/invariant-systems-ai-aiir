# AIIR CLI subcommands

AIIR's CLI accepts two equivalent forms:

- **Flat flags** (canonical, fully backward-compatible): `aiir --verify <file>`,
  `aiir --ci`, `aiir --pretty`, … Everything the GitHub Action, GitLab CI
  templates, the pre-commit hook, and existing scripts use. These will keep
  working.
- **Discoverable verbs** (sugar): `aiir verify <file>`, `aiir ci`, … Friendlier
  to discover and type. They rewrite to the canonical flat flags, so behavior is
  identical.

## Available verbs today

| Verb | Equivalent | Notes |
|------|------------|-------|
| `aiir quickstart` / `aiir setup` | `--quickstart` | first-run scaffold |
| `aiir status` | `--status` | ledger/repo status |
| `aiir ci` | `--ci` | CI gate |
| `aiir check` | `--check` | policy check |
| `aiir verify <file>` | `--verify` | verifies commit, review, **and agent** receipts |
| `aiir stats` | `--stats` | ledger dashboard |
| `aiir badge` | `--badge` | shields.io badge |
| `aiir doctor` | `--doctor` | diagnostics |
| `aiir init` | `--init` | scaffold `.aiir/` |
| `aiir trailer` | `--trailer` | commit trailer output |
| `aiir install-hook` | `--install-hook` | install post-commit hook |
| `aiir agent emit` | *(nested subcommand)* | emit an agent receipt (`aiir/agent_receipt.v0.1`) |
| `aiir agent verify <file>` | *(nested subcommand)* | verify an agent receipt |

`aiir agent` is a **real nested subcommand** with its own clean flags
(`--action/--tool/--kind/--surface/--session/--intent/--summary/--input/--output/
--policy/--policy-reason/--policy-contract`), not a flat-flag rewrite. It is the
reference pattern for the restructure below.

## Roadmap — full subcommand restructure (deferred)

The discoverable-verb surface above is a **partial** restructure. The full
migration is intentionally deferred (it is UX polish, larger and higher-churn
than the agent-receipt wedge it was sequenced behind). When picking it up:

1. **Re-run the CLI-restructure scoping** first (the prior scoping agent died on
   a transport error, so the detailed design was never captured). Produce the
   subcommand tree, the per-verb flag groupings, and the backward-compat shim
   design.
2. **Model every verb on `aiir agent`** (`main()` early-dispatch → a dedicated
   handler with its own argparse subparser). Candidates not yet nested:
   `receipt`/`generate` (the default mode, optionally with `--range`),
   `verify-release`, `export`, `review`, `commitment`, `policy`/`policy-init`,
   and the sign/in-toto options as flags under `receipt`.
3. **Keep all flat flags working.** They are the canonical, backward-compatible
   form (used by `action.yml`, `templates/*`, pre-commit, and every existing
   user). The restructure adds verbs; it must not remove or break flags. A
   deprecation horizon for the flat form (if any) is a separate decision.
4. **Extract per-subcommand handlers** out of the ~3k-line `main()` to keep it
   maintainable, and give each verb its own `--help`.
5. **Tests:** every existing flat invocation must still produce identical
   behavior (the current CLI tests must pass unchanged), plus new tests for each
   verb form. Maintain the 100% line+branch coverage gate.

Code breadcrumbs point here from `aiir/cli.py` (`_expand_shorthand_command` and
the `agent` dispatch in `main()`).
