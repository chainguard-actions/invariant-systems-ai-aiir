<!-- markdownlint-disable -->

# Hardening Report: invariant-systems-ai--aiir/v1.7.0

> This file was generated automatically by the hardening agent.

**Policy SHA:** `d636be7e43ef829af6e853da6b3c7566db9f72fe`

**Test Policy SHA:** `843adf9e4b8f85d0c08b27b9d0b09dd094b54702`

**Harden Agent Version:** `1`

Action **invariant-systems-ai--aiir/v1.7.0** was hardened automatically. 1 finding(s) were identified and resolved across 1 iteration(s).

## Findings Fixed

### github-env-injection (severity: high)

In the 'Determine commit range' step of action.yml, the variable $RANGE (derived from untrusted inputs: inputs.commit-range, github.event.pull_request.base.sha, github.event.pull_request.head.sha, github.event.before, github.event.after) is written to $GITHUB_OUTPUT without the required sanitization step (`printf '%s' ... | tr -d '\n\r'`). While the script validates $RANGE against control characters using grep before writing, this is not the required sanitization pattern. The write uses a heredoc delimiter pattern: `echo "range<<${DELIM}"` / `echo "$RANGE"` / `echo "${DELIM}"` >> "$GITHUB_OUTPUT"`. An attacker who can supply a commit-range input or manipulate the github event payload with embedded newlines could potentially inject additional output variables.

Locations:

- `action.yml:98`

## Iteration Notes

### Iteration 1

**Fixes applied:** github-env-injection

**Notes:**

Fixed the github-env-injection finding in the 'Determine commit range' step of action.yml (line 98). Added `SAFE_RANGE=$(printf '%s' "$RANGE" | tr -d '\n\r')` to sanitize the RANGE value before writing to $GITHUB_OUTPUT, and updated the heredoc to use `$SAFE_RANGE` instead of `$RANGE`. This prevents potential injection of additional output variables via embedded newlines in attacker-controlled inputs (commit-range input or github event payload values).

