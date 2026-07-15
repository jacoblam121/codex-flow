# Phase 05: Repair and Run Lineage

## Outcome

Turn an accepted Sol audit into one of three explicit repair paths while preserving the original plan, execution evidence, audit findings, and
model-selection discipline.

## Prerequisites

- Phase 04 is accepted.
- The selected run has a complete structured Sol audit or an explicitly acknowledged repository-only/unstructured audit.

## In Scope

- Create each repair's immutable launch manifest with parent/root lineage and repair strategy; do not rewrite the historical parent manifest.
- Extract the latest complete `<codex_flow_audit run_id="...">` for the selected run from the source Sol rollout and persist valid JSON as
  `audit.json`.
  When no valid envelope exists, require the user to confirm the exact audit findings text that will be handed to repair.
- Implement the repair menu with these choices:
  - Fresh linked run, recommended by default.
  - New tab forked from the previous execution thread.
  - Sol fixes directly in the source control thread.
- Fresh linked repair:
  - Start a clean Codex context.
  - Include the original approved plan, prior execution report when valid (otherwise labeled unstructured execution result), confirmed Sol audit,
    current live repository state, and narrowly stated repair objective.
- Execution-context repair:
  - Use `codex fork <execution-thread-id>` rather than concurrent resume.
  - Add the Sol audit and current state in the new initial repair prompt.
- Sol-fix repair:
  - Do not launch another process.
  - Require Default mode and explicit confirmation that Sol may stop being read-only for this repair.
  - Name the shared-worktree risk and require confirmation that no execution tab is currently running an editing turn. Do not claim to detect
    idleness, add a writer lock, or treat an open TUI process as proof of activity.
- Re-run the Pareto model recommendation and user confirmation for every execution repair launch.
- Preserve the same structured report contract for repairs and make subsequent reviews select the child run.
- Allow repeated repair/review cycles without losing the root plan or confusing reports between generations.

## Contracts

- Every repair run has exactly one parent run and shares the root plan hash.
- Never mutate a historical report or audit when creating a repair.
- Forking an execution context reuses history through a new thread; sending a prompt into the existing live execution TUI is not supported.
- Sol-fix uses the current Sol model. The skill cannot silently change it.
- A repair prompt contains only the accepted findings and current evidence; do not broaden it into a fresh implementation plan.
- A missing model-emitted envelope never causes Codex Flow to invent findings; only user-confirmed audit text may replace it.

## Tests

- Fresh repair from completed, partial, and blocked parent runs.
- Execution-context fork with missing, closed, or ambiguous execution thread.
- Sol-fix requested from Plan mode and Default mode.
- Sol-fix accepted/rejected with another execution tab still open, including the explicit idle-turn confirmation.
- Repaired worktree whose baseline is intentionally dirty from the parent run.
- Multi-generation lineage and report/audit selection.
- Model re-recommendation, manual override, rejection, and approved escalation.
- Parent report or audit missing/malformed.

## Exit Criteria

- Each menu path operates as specified and leaves an inspectable lineage.
- A second review retrieves the repair report rather than the original report.
- The original Sol planning thread remains available throughout execution repair paths.
- No path opens the same session concurrently in two TUIs.
- Tests demonstrate at least three generations without ID or artifact collision.

## Explicitly Deferred

- Automated repair selection.
- Direct remote-control injection into live execution tabs.
- Concurrent worktree isolation or writer locks.
- Grounded Markdown plan bundles.

## Required Executor Report

Report lineage fields, repair prompt composition, all three path results, multi-generation tests, failure handling, and remaining concurrency
risks.
