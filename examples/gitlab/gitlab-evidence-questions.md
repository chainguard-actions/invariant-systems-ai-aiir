# GitLab AI Provenance Evidence: Questions

Questions that the `gitlab_ai_provenance_evidence.v0` artifact can help
answer, grouped by what is available today versus what requires future
tooling or custom data.

These are high-level question intents for a GitLab project owner. They
reference ordinary GitLab entities (Project, Merge Request, Pipeline, Job,
commit SHA, changed files, artifact) and the fields in
`aiir-evidence.example.json`. No Orbit query syntax, node/edge definitions,
ingestion design, or graph projection guidance is provided here.

---

## 1. Current GitLab artifact/API questions

Questions answerable today using GitLab CI artifacts, the GitLab API, and
standard JSON tooling (e.g. `jq`). These align with the kinds of questions
a GitLab project owner or security team would ask using existing GitLab
data surfaces.

**Which AI-declared MRs have a valid receipt associated with their head pipeline?**

Look for `aiir-evidence.json` artifacts where
`provenance.declared_ai_involvement` is `true` and
`receipt.verification_status` is `valid`. Cross-reference by
`subject.merge_request_iid` and `subject.pipeline_sha`.

**Which AI-declared changes merged without a valid receipt artifact?**

Identify MRs where `provenance.declared_ai_involvement` is `true` but no
`aiir-evidence.json` artifact exists for the head pipeline, or where
`receipt.verification_status` is `unverified` or `invalid` at merge time.

**Which projects have AI-declared commits but no CI verification job?**

Identify projects where commits carry AI signals (e.g. `Co-authored-by`
trailers) but no pipeline artifact with `schema: gitlab_ai_provenance_evidence.v0`
was produced for the corresponding MR pipeline.

**Which AI-declared MRs failed security scans after the receipt was generated?**

Cross-reference `aiir-evidence.json` artifacts (filtered to
`provenance.declared_ai_involvement: true`) with GitLab Security Dashboard
findings for the same pipeline. Security scan results are separate GitLab
data; this question is a read-side join on existing GitLab artifacts, not
a new field in the v0 evidence artifact.

**Which AI-declared MRs touched authentication or authorization paths?**

Filter `aiir-evidence.json` artifacts where
`provenance.declared_ai_involvement` is `true` and
`change.files_changed` contains paths matching patterns such as
`auth/`, `session`, `oauth`, `permission`, or `rbac`.

---

## 2. Future/custom-data questions

Questions that require additional tooling, custom data pipelines, or future
GitLab graph capabilities beyond what is available in standard CI artifacts
today.

**Which AI-declared changes touched files associated with critical vulnerabilities?**

This requires correlating `change.files_changed` in the evidence artifact
with vulnerability findings that reference specific file paths. GitLab
Vulnerability findings and Security scan results are separate data; a
file-level join between evidence artifacts and vulnerability records is a
future/custom-data capability. The v0 artifact does not include vulnerability
data or file-level risk scores.
