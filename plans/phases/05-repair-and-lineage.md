# Phase 05: Repair and Run Lineage

## Outcome

Turn a user-requested, confirmed repair brief from a conversational Sol review into one of three explicit repair paths while preserving the
original plan, execution evidence, review context, and model-selection discipline.

## Prerequisites

- Phase 04 is accepted.
- The selected run has been conversationally reviewed, and the user has explicitly requested repair.
- A repair brief has been captured and confirmed by the user; review findings alone never authorize repair.

## In Scope

- Create each repair's immutable launch manifest with parent/root lineage and repair strategy; do not rewrite the historical parent manifest.
- Capture the user-confirmed repair brief only when repair is requested. The brief may cite conversational findings and exact live evidence, but
  Codex Flow must not invent findings or persist a Phase 04 review envelope.
- Implement the repair menu with these choices:
  - Fresh linked run, recommended by default.
  - New tab forked from the previous execution thread.
  - Sol fixes directly in the source control thread.
- Fresh linked repair:
  - Start a clean Codex context.
  - Include the original approved plan, prior execution report when valid (otherwise labeled unstructured execution result), confirmed repair brief,
    current live repository state, and narrowly stated repair objective.
- Execution-context repair:
  - Use `codex fork <execution-thread-id>` rather than concurrent resume.
  - Add the confirmed repair brief and current state in the new initial repair prompt.
  - Persist the expected execution-thread fork origin in the repair manifest so later association can require the exact origin.
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
- Never mutate a historical report or conversational review when creating a repair.
- Forking an execution context reuses history through a new thread; sending a prompt into the existing live execution TUI is not supported.
- Sol-fix uses the current Sol model. The skill cannot silently change it.
- A repair prompt contains only the user-confirmed repair brief and current evidence; do not broaden it into a fresh implementation plan.
- A missing or malformed model-emitted report never causes Codex Flow to invent findings. User confirmation is required before any repair launch.
- A repair fork manifest records the expected source execution-thread origin exactly; later rollout association rejects a different origin.

## Tests

- Fresh repair from completed, partial, and blocked parent runs.
- Execution-context fork with missing, closed, or ambiguous execution thread and wrong fork origins.
- Sol-fix requested from Plan mode and Default mode.
- Sol-fix accepted/rejected with another execution tab still open, including the explicit idle-turn confirmation.
- Repaired worktree whose baseline is intentionally dirty from the parent run.
- Multi-generation lineage and exact report selection.
- Model re-recommendation, manual override, rejection, and approved escalation.
- Parent report missing/malformed and user-confirmed repair brief handling.

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
