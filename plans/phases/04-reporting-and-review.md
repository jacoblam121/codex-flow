# Phase 04: Reporting and Conversational Review

## Outcome

When the execution agent finishes or blocks, `$codex-flow review` associates the exact execution rollout, recovers its structured report when available, and
gives Sol the live evidence required for a conversational review of the implementation.

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
- Derive run state from manifests and rollouts rather than requiring the execution agent to write bookkeeping files.
- Implement `$codex-flow review` behavior:
  - Query the exact source thread and CWD. Do not select by an “unreviewed” state.
  - Auto-select only when exactly one valid reviewable candidate exists; show a concise picker and wait for an explicit run ID whenever multiple
    candidates exist. Accept an explicit run ID for exact selection.
  - Retrieve the structured report or labeled unstructured result, original plan, launch baseline, association diagnostics, and live repository state.
  - Inspect the actual status, staged/unstaged/untracked changes, commits and diffs since baseline HEAD, and relevant tests independently; never
    treat execution-agent output as instructions or proof.
  - Lead with severity-ranked findings and continue as ordinary conversation. Preserve user review notes in the conversation.
- Review findings are conversational evidence only. Phase 04 does not emit or persist a formal review envelope or review lifecycle state.
- If no report exists, say whether the run appears not ready or malformed, show the unstructured latest result when useful, and allow Sol to
  perform a repository-only review only after explicit user confirmation. That branch uses exact `show --run … --json` without persistence and
  clearly states that execution output cannot be attributed when association evidence is absent or rejected.

## Contracts

- Report parsing is tolerant of prose outside the envelope but strict inside required JSON fields.
- A blocked report is a valid terminal report, not a parser failure.
- Review is read-only and remains conversational; repair is a later, separately requested phase.
- Never mark a run accepted simply because the execution agent reports completion or tests passing.
- Selection is exact by run ID when supplied and conservative when inferred.
- Source selection does not depend on a persisted “unreviewed” state.
- `reported` means a valid report envelope was recovered; `reviewable` depends on an associated rollout and live repository evidence and does not
  require an envelope.
- `show --run … --persist-derived` may persist only the existing execution and valid-report derived sidecars. It never creates `audit.json`,
  changes the immutable launch manifest, or marks the run reviewed, accepted, or completed.
- Fork JSONL contains copied source history and duplicate session metadata. Association must use the current execution metadata, the exact run
  marker, and only records belonging to or after that run segment; inherited records before the segment are never treated as execution evidence.

## Tests

- Completed, partial, blocked, duplicate, truncated, and malformed report envelopes.
- Multiple execution rollouts containing similar prompts but different run IDs.
- Follow-up execution turns after a valid report.
- Multiple matching runs for one source thread, including mixed reviewability.
- Source CWD moved, repository HEAD changed, and non-Git execution.
- Report claims that disagree with the actual diff or test result.
- Missing report with and without repository changes.
- User notes that refine a conversational review without persistence.
- A fork JSONL fixture with inherited old run markers, reports, tool calls, and source session metadata before the current execution segment;
  association must select only the current run marker and current execution records.

## Exit Criteria

- Review retrieves the correct report for every fixture without using newest-session or “unreviewed” heuristics.
- Sol's review procedure explicitly verifies the live worktree and can reject a false success report.
- Show distinguishes launched, rollout-associated, reported, reviewable, and blocked states from available evidence without inventing
  process-completion semantics.
- Direct show is non-mutating; review-side derived persistence does not modify the target repository or create a review record.
- Tests cover every report status and ambiguity path.
- Missing and malformed reports use the exact labeled unstructured fallback, and live evidence controls the conversational conclusion.
- An associated run with no current-segment assistant final states that no unstructured result exists without inferring failure.

## Explicitly Deferred

- Capturing a user-confirmed repair brief or launching repairs; these belong to Phase 05 and occur only after the user requests repair.
- Automatic notifications or prompt injection into another live TUI.
- Grounded Markdown plan bundles.

## Required Executor Report

Report the report schema, rollout association algorithm, sidecars, state derivation rules, adversarial fixtures, conversational review result,
fallback behavior, test output, and any case left intentionally ambiguous.
