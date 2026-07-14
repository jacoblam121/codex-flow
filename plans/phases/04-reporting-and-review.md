# Phase 04: Reporting and Review

## Outcome

When Luna finishes or blocks, `$codex-flow review` associates the exact execution rollout, recovers its structured report when available, and
gives Sol the live evidence required to audit the implementation independently.

## Prerequisites

- Phase 03 is accepted.
- Execution handoffs already include the run marker and report contract.

## In Scope

- Finalize the best-effort machine-locatable report envelope:
  - `<codex_flow_report run_id="...">...</codex_flow_report>`.
  - The body is versioned JSON.
  - Status is exactly `completed`, `partial`, or `blocked`.
  - Required fields cover summary, files changed, commands/tests and outcomes, deviations, unresolved issues, and recommended follow-up.
- Locate the execution rollout by the run marker in its initial user prompt and validate it against launch time and CWD metadata.
- Persist discovered execution-thread metadata in atomic `execution.json`; never mutate the immutable launch manifest.
- Extract the latest complete report envelope for the run, not merely the latest assistant response.
- Persist valid recovered report JSON separately as `report.json`. If the envelope is absent or malformed, retain a pointer to the exact latest
  assistant final result as unstructured context without treating it as a valid report.
- Implement one read-only CLI inspection surface:
  - `codex-flow show --run <id> --json` for one exact run.
  - `codex-flow show --source-thread <id> --cwd <path> --json` for conservative run selection/listing.
- Derive run state from manifests and rollouts rather than requiring Luna to write bookkeeping files.
- Implement `$codex-flow review` behavior:
  - Choose the latest unreviewed run for the current source thread and repository.
  - Show a picker if more than one run is plausible.
  - Retrieve the structured report or labeled unstructured result, plan, baseline, and live Git state.
  - Inspect the actual diff and relevant tests independently; never treat Luna's report as proof.
  - Ask Sol to emit `<codex_flow_audit run_id="...">...</codex_flow_audit>` with versioned JSON inside the envelope.
- The audit must lead with severity-ranked findings, cite file/line evidence when possible, list validation performed, state a verdict, and identify
  required repair scope.
- If no report exists, say whether the run appears not ready or malformed, show the unstructured latest result when useful, and allow Sol to
  perform a repository-only audit when the user requests it.

## Contracts

- Report and audit parsing is tolerant of prose outside the envelopes but strict inside required JSON fields.
- A blocked report is a valid terminal report, not a parser failure.
- Review is read-only unless the user later selects the Sol-fix repair path.
- Never mark a run accepted simply because Luna reports completion or tests passing.
- Selection is exact by run ID when supplied and conservative when inferred.
- `reported` means a valid report envelope was recovered; `reviewable` depends on an associated rollout and live repository evidence and does not
  require an envelope.
- Fork JSONL contains copied source history and duplicate session metadata. Association must use the current execution metadata, the exact run
  marker, and only records belonging to or after that run segment; inherited records before the segment are never treated as execution evidence.

## Tests

- Completed, partial, blocked, duplicate, truncated, and malformed report envelopes.
- Multiple execution rollouts containing similar prompts but different run IDs.
- Follow-up Luna turns after a valid report.
- Multiple unreviewed runs for one source thread.
- Source CWD moved, repository HEAD changed, and non-Git execution.
- Report claims that disagree with the actual diff or test result.
- Missing report with and without repository changes.
- Missing/malformed audit envelope after an otherwise complete Sol review.
- A fork JSONL fixture with inherited old run markers, reports, tool calls, and source session metadata before the current execution segment;
  association must select only the current run marker and current execution records.

## Exit Criteria

- Review retrieves the correct report for every fixture without using newest-session heuristics.
- Sol's review procedure explicitly verifies the live worktree and can reject a false success report.
- Show distinguishes launched, rollout-associated, reported, reviewable, blocked, and audited states from available evidence without inventing
  process-completion semantics.
- Review and show do not modify the target repository.
- Tests cover every report status and ambiguity path.
- One approved real Luna run measures whether report and audit envelopes are recovered; failure exercises and accepts the repository-only
  fallback rather than blocking the workflow.

## Explicitly Deferred

- Launching repairs or forking the execution thread.
- Automatic notifications or prompt injection into another live TUI.
- Grounded Markdown plan bundles.

## Required Executor Report

Report the report/audit schemas, rollout association algorithm, sidecars, state derivation rules, adversarial fixtures, real-run envelope result,
fallback behavior, test output, and any case left intentionally ambiguous.
