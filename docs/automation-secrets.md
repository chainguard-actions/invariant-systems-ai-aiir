# AIIR Automation Secrets

AIIR keeps long-lived automation credentials in one canonical operator-managed
location and one CI delivery plane:

1. Canonical local vault: `~/.config/kaleidos/secrets.env`
2. GitHub Actions environment: `automation-secrets`

The public repo contains only metadata about those secrets in
`.github/automation-secrets.json`. No values belong in git history.

## Why this exists

- Repo secrets are easy to accumulate and hard to audit.
- CI failures should be repairable from one source of truth.
- The same secret should not need to be remembered across shell history,
  ad hoc notes, and forge settings.

## Inventory

| Secret | Canonical key | Delivery target | Notes |
|--------|---------------|-----------------|-------|
| `GITLAB_TOKEN` | `GITLAB_TOKEN` | GitHub environment `automation-secrets` | GitHub to GitLab mirror sync |
| `NPM_TOKEN` | `NPM_TOKEN` | GitHub environment `automation-secrets` | npm publish |
| `WEBSITE_DISPATCH_TOKEN` | `WEBSITE_DISPATCH_TOKEN` | GitHub environment `automation-secrets` | Website dispatches |
| `TRAFFIC_TOKEN` | `TRAFFIC_TOKEN` | GitHub environment `automation-secrets` | Traffic archive job |
| `VSCE_PAT` | `VSCE_PAT` | GitHub environment `automation-secrets` | Marketplace publish |
| `OVSX_PAT` | `OVSX_PAT` | GitHub environment `automation-secrets` | Optional Open VSX publish |

`VSCE_PAT` also accepts compatibility source aliases from the canonical vault:
`AZURE_DEV_PAT`, `AZURE_DEVOPS_PAT`, and `ADO_PAT`.

## Sync

Check which secrets are present in the canonical vault and whether they can be
applied:

```bash
python3 scripts/sync_ci_secrets.py --check
```

Apply all available secrets into the GitHub Actions environment:

```bash
python3 scripts/sync_ci_secrets.py --apply
```

If the live workflow still expects a temporary repo-level bridge secret, apply
that bridge as well:

```bash
python3 scripts/sync_ci_secrets.py --apply --sync-repo-bridge
```

## Recovery model

When a PAT or token is revoked, expired, or missing:

1. Fix the value once in `~/.config/kaleidos/secrets.env`.
2. Rerun `python3 scripts/sync_ci_secrets.py --apply`.
3. Rerun the failed workflow.

That makes the repair path explicit and repeatable instead of requiring manual
forensics across repo settings, shell history, and local editor state.
