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

## Later Sol audit

Future Sol audits use a run-linked, versioned audit envelope tied to the exact run marker and current repository evidence. Recovery, parsing, persistence, and review of that audit belong to Phase 04. Do not implement those workflows here.

Do not add an audit envelope to the execution agent's response in this phase. Do not extract reports, persist recovery sidecars, or review execution results now; the existing launcher handoff's best-effort report request is the complete Phase 03 contract.
