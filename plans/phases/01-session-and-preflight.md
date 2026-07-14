# Phase 01: Session and Preflight Core

## Outcome

Given the live source thread and working directory, resolve the exact root rollout and current native mode, extract the last approved plan,
validate a requested model selection, and return a reproducible Git/environment preflight record without launching or writing a run.

## Prerequisites

- Phase 00 is accepted.
- The executor has representative Codex rollout fixtures and access to the installed `codex` command.

## In Scope

- Locate a rollout by exact thread ID beneath `$CODEX_HOME/sessions/**`.
  - Match the thread ID in the rollout filename and confirm it from session metadata.
  - Confirm the source is the root interactive thread, not a subagent rollout.
  - Never select a rollout by newest modification time alone.
  - Reject zero or multiple exact matches with actionable diagnostics.
- Parse JSONL defensively.
  - Ignore unknown record and payload types.
  - Count malformed lines and surface warnings.
  - Fail if malformed data prevents proving a required result.
- Read the latest `turn_context.payload.collaboration_mode.mode` and return `plan`, `default`, or an explicit unsupported/unknown result.
- Extract the latest approved plan:
  - Prefer the latest complete `event_msg` `item_completed` whose `item.type == "Plan"`.
  - Cross-check it against the corresponding assistant `response_item` whose message has `phase == "final_answer"` and contains a complete
    `<proposed_plan>...</proposed_plan>` block.
  - Use the tagged final answer as a compatibility fallback when the structured item is absent; warn on a one-source fallback and fail on a
    content mismatch rather than guessing.
- Preserve the plan text, calculate its SHA-256 hash, and return a short title/preview for confirmation.
- Inspect Git without changing it:
  - Exact CWD and repository root.
  - Branch or detached-HEAD state.
  - HEAD commit when present.
  - Porcelain status, including untracked paths.
  - A stable baseline fingerprint used to detect changes between preflight and launch.
- Support non-Git directories with an explicit reduced-audit warning rather than failure.
- Read the version-characterized `codex debug models --bundled` JSON and expose supported model/effort combinations. Treat the command as an
  experimental compatibility surface and fail actionably when its shape no longer matches rather than silently accepting an unknown pair.
- Implement `codex-flow preflight --thread <id> --cwd <path> --json` as a read-only command.

## Contracts

- Prefer the explicit `--thread`; fall back to `CODEX_THREAD_ID` only when the argument is absent.
- Resolve the working directory from explicit `--cwd`, then the caller's CWD. Never derive it from the rollout without showing a mismatch.
- Treat invoking handoff after the user received the plan as approval intent, but still show the extracted plan hash before launch.
- For structured/tagged cross-checking, normalize line endings and remove only the tag-adjacent wrapper newline; do not collapse meaningful plan
  whitespace before comparing or hashing the canonical text.
- Handoff may launch only when preflight reports `default`; the launcher does not infer mode from user prose.
- The baseline fingerprint covers repository identity, HEAD, and porcelain status. Launch must recompute it.
- Model validation is runtime-derived. The Pareto recommendation policy remains in the skill, not the parser.

## Tests

- Root and subagent rollouts created at nearly identical times.
- Multiple structured and tagged assistant plans with only the latest matching pair selected.
- A structured-only plan, tagged-only fallback, and a structured/tagged mismatch.
- Plan -> Default followed by later final answers that do not contain plan tags; the approved plan remains selected.
- Plan, Default, missing, and unknown collaboration-mode records.
- Missing, truncated, nested-looking, and malformed plan tags.
- Unknown JSONL events and isolated malformed lines.
- Exact filename match whose session metadata contains a different thread ID.
- Clean, dirty, detached, unborn, worktree, and non-Git directories.
- Model catalog with supported and unsupported reasoning levels.
- Paths containing spaces and Unicode.

## Exit Criteria

- The preflight fixture always selects the intended root plan even when a newer subagent rollout exists.
- Preflight reports the exact current mode and rejects a handoff from Plan or an unsupported mode before run creation.
- Preflight produces stable JSON across repeated calls with unchanged state.
- Changing HEAD or status changes the baseline fingerprint.
- Unsupported model/effort requests fail before any run state is written.
- All tests pass without opening Windows Terminal.

## Explicitly Deferred

- Creating run directories or prompts.
- Launching plan-only or forked sessions.
- Report and audit extraction beyond reusable low-level JSONL iteration.
- Grounded Markdown plan bundles.

## Required Executor Report

Report the exact rollout records used as sources of truth, preflight JSON shape, fixture coverage, test output, and unresolved format assumptions.
