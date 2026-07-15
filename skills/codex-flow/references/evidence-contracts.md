# Evidence contracts

Use repository evidence as the authority for execution results.

## Run association

The exact run marker is the versioned self-closing element emitted by the accepted launcher:

```text
<codex_flow_run run_id="<validated UUID>" version="1" />
```

It associates the execution work and later evidence with one run. Preserve the exact run ID.

## Best-effort report

The existing versioned `<codex_flow_report run_id="…">` envelope is best effort. A missing, malformed, incomplete, or unparseable report does not prove failure. Repository state, diffs, and tests remain authoritative. Do not infer completion from the envelope alone.

## Conversational review

Conversational review is not a persisted run state. It uses the exact run JSON, the immutable plan and launch manifest, rollout association
diagnostics, and independently inspected live repository evidence in the current Sol conversation. Review findings and user notes remain
conversation content only.

Do not add a `codex_flow_audit` envelope, create `audit.json`, or mark a run audited, reviewed, accepted, or completed. The review-side `show --run … --persist-derived` operation may persist only the existing execution and valid-report derived sidecars. It does not mutate the
immutable launch manifest or target repository.

The execution report remains best-effort transport. A malformed or missing report falls back to the exact latest assistant result with an explicit
unstructured label; neither form is proof of correctness. Live repository state, diffs, commits, and independently selected tests remain the
authority for review conclusions.

When association evidence is missing, malformed, or ambiguous, a repository-only review requires explicit user confirmation and uses exact
`show --run … --json` without derived persistence. Execution output is then unattributed context, not evidence for that run. An associated run
may also have no current-segment assistant final; in that case the review reports that no unstructured result was observed and does not infer
failure.
