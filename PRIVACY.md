# Privacy Data Handling — AIIR Commit Receipts

This document describes what personal data AIIR commit receipts contain, how
that data is processed, and the privacy controls available to operators and
contributors.

---

## What personal data receipts contain

By default, every AIIR commit receipt includes the following personal data in
its **hashed core** (`CORE_KEYS`):

| Field | Data | Hashed? | Notes |
|-------|------|---------|-------|
| `commit.author.name` | Git author display name | Yes (in core) | May be a real name |
| `commit.author.email` | Git author email address | Yes (in core) | Typically a work or personal email |
| `commit.committer.name` | Git committer display name | Yes (in core) | Usually same as author |
| `commit.committer.email` | Git committer email address | Yes (in core) | Usually same as author |
| `commit.subject` | First line of commit message | Yes (in core) | May contain names or identifiers |
| `commit.message_hash` | SHA-256 of full commit message | Yes (in core) | Hash only; message not stored |
| `commit.diff_hash` | SHA-256 of the diff | Yes (in core) | Hash only; diff not stored |
| `commit.files` | List of changed file paths | Yes (in core) | May reveal project structure |
| `commit.sha` | Git commit SHA | Yes (in core) | Public identifier |

Because these fields contribute to `content_hash` and `receipt_id`, they
**cannot be changed or removed** without invalidating the receipt. This is
the tamper-evidence property.

---

## Content-hash / erasure tension (GDPR Art. 17)

AIIR receipts are content-addressed. Any modification to a core field,
including removing or replacing an email address, changes `content_hash`
and `receipt_id`, breaking verification of the original receipt.

This creates a structural tension with the **right to erasure** (GDPR Art. 17)
and similar data-protection rights:

- **Redacting email after the fact** creates a new, non-verifiable receipt:
  the original receipt_id no longer matches.
- **Receipts published to transparency logs** (Rekor, SCITT) cannot be deleted
  from those logs by design. Erasure is not technically achievable for
  log-submitted receipts.

**Recommended approach for GDPR-regulated deployments:**

1. Decide on redaction policy *before* generating receipts.
2. Use `--redact-emails` at generation time so email pseudonyms are baked into
   the hashed core from the start (see below).
3. Treat the resulting receipts as the authoritative record. Do not re-generate
   unredacted versions and compare them.
4. Do NOT submit unredacted receipts to public transparency logs if contributors
   are likely to exercise GDPR erasure rights in the future.

---

## `--redact-emails`: per-ledger HMAC pseudonymization

When `--redact-emails` is passed, AIIR replaces author and committer email
addresses with a per-ledger HMAC-SHA256 pseudonym before hashing:

```text
normalized = strip_terminal_escapes(email).strip().lower()
pseudonym  = "redacted+" + HMAC-SHA256(ledger-salt, normalized)[:16] + "@users.noreply.aiir"
```

**Properties:**

| Property | Behaviour |
|----------|-----------|
| **Pseudonymous, not anonymous** | The same email + same salt = same pseudonym |
| **Per-ledger isolation** | Different ledger salts produce different pseudonyms for the same email |
| **Reproducible within a ledger** | A re-generated receipt under the same salt produces the same receipt_id |
| **Cross-ledger non-linkability** | You cannot correlate the same contributor across different ledgers |

**The salt lives in `.aiir/config.json`** (mode 0600) under the key
`redaction_salt`. It is a 256-bit random value generated at ledger
initialization. **Back it up**: without the salt you cannot reproduce the
pseudonymized receipt IDs.

> **The unlinkability properties above hold only with a secret per-ledger
> salt.** The CLI `--redact-emails` path always supplies one. If AIIR is used
> as a library without a ledger salt, a fixed *public* fallback constant is
> used instead, and that path is **not** unlinkable and is dictionary-reversible
> (anyone can recompute the token for a guessed email). Keep `redaction_salt`
> secret; treat it like a key, not like an `instance_id`.

```json
// .aiir/config.json (excerpt)
{
  "instance_id": "8ef04f9d-...",
  "redaction_salt": "a3b9c4d2e1f0..."   // 64 hex chars (256 bits)
}
```

> **Warning**: Do not share `.aiir/config.json` outside your organization.
> The `redaction_salt` is secret material. `aiir --export` explicitly omits
> the salt from exported bundles, but any manual copy or backup of config.json
> should be treated as sensitive.

---

## Transparency-log permanence

If you sign receipts with Sigstore (`--sign`) and submit them to Rekor (the
default), the receipt JSON and signature are written to a public, append-only
transparency log. **Entries in Rekor cannot be deleted.**

This means:

- Unredacted email addresses in signed receipts become permanently public.
- Even if you delete the receipt from your local ledger or repository, the
  Rekor entry remains.

**Use `--redact-emails` before signing** if any contributor email addresses
should not be publicly logged.

---

## File paths (`--redact-files`)

The `commit.files` field lists up to 100 changed file paths. In some
deployments, file paths may constitute personal data (e.g., user-specific
directories) or reveal sensitive project structure.

Use `--redact-files` to omit the file list from the receipt. The
`files_changed` count is still recorded; only the path list is omitted.
`--redact-emails` and `--redact-files` may be combined.

---

## README documentation

See [`README.md`](README.md) for the `--redact-emails` and `--redact-files`
CLI flags.

---

## Contact

For data-handling questions or GDPR requests related to the AIIR project:

- Email: [noah@invariantsystems.io](mailto:noah@invariantsystems.io)
- Security reports: see [SECURITY.md](SECURITY.md)
