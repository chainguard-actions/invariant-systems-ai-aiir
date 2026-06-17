# Deterministic Smoke Coverage

This release gate is dual-track.

- Human smoke confirms operator comprehension, packaged-VSIX presentation, and misleading-feel checks.
- Deterministic smoke confirms command routing, recovery behavior, summary output shape, and repository targeting.

Every blocking ship decision should cite both this file and the human run artifact.

## Blocking Coverage Map

| Blocking check | Deterministic confirmation | Human confirmation still required |
| --- | --- | --- |
| `AIIR: Record Commit Activity` behaves like one flow on first use | `extensions/vscode/test/extension-host/suite/commands.test.js`: `auto-initializes the repository when generatePreferred is run on first use` | Verify the packaged extension feels like one action rather than setup choreography |
| Successful recording offers the most useful next action first | `extensions/vscode/test/extension-host/suite/commands.test.js`: `surfaces a PR-ready summary after generation` | Judge whether the prompt wording feels obvious to a first user |
| Copied summary is PR-ready | `extensions/vscode/test/extension-host/suite/commands.test.js`: `surfaces a PR-ready summary after generation`; `extensions/vscode/test/navigation_surface.test.js`: `receipt generation closes with view, copy, and automation next steps` | Paste the summary into a real PR or issue draft and check readability |
| Explicit setup resumes the blocked action instead of dead-ending | `extensions/vscode/test/extension-host/suite/commands.test.js`: `resumes a pending generate action after CLI availability is restored`; `extensions/vscode/test/navigation_surface.test.js` pending-action expectations | Verify the transition feels natural in the packaged extension |
| Repository focus switching retargets AIIR surfaces | `extensions/vscode/test/extension-host/suite/commands.test.js`: `switches repository focus for untargeted commands`; `extensions/vscode/test/navigation_surface.test.js` command-surface assertions | Confirm Coverage, Status, and Receipts all look aligned after switching |
| Commit-status wording is visible across the shell | `extensions/vscode/test/navigation_surface.test.js`; `extensions/vscode/test/package_manifest.test.js` | Confirm the phrasing is legible and non-misleading in the packaged UI |

## Required Deterministic Commands

Run these before treating the human deep smoke as ship-ready evidence.

```bash
cd extensions/vscode
npm test
npm run test:extension-host
```

## Ship Rule

Do not mark the release ready if either side is missing:

- no human artifact for the packaged-VSIX pass
- no green deterministic proof for the mapped blocking checks above
