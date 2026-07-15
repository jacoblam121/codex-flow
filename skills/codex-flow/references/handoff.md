# Handoff workflow

Use this workflow for `$codex-flow handoff` and equivalent explicit requests to hand off an approved plan. Do not use it for an explanation-only question.

## Intent boundary

1. Distinguish the request before doing work. For an explanation, describe Codex Flow and its boundaries only; do not run a command, open a terminal, or launch a TUI. For explicit handoff intent, begin preflight, but do not launch.
2. The initial handoff request is never confirmation. After rendering a proposal, wait for a later plain conversational response. Do not depend on `request_user_input`.

## Preflight and evidence

Run the absolute installed/development CLI against the invoking root thread and the exact absolute current working directory:

```text
/home/jacob/.local/bin/codex-flow preflight --thread "$CODEX_THREAD_ID" --cwd "$EXACT_CWD" --json
```

Require `CODEX_THREAD_ID` and capture the invoking CWD exactly. Parse JSON stdout even when the command exits `3` for a recognized failed precondition. Stop with an actionable diagnostic when the command is unavailable, stdout is malformed, the catalog is unsupported, the approved plan evidence is missing or malformed, or any other required evidence is invalid. Reuse this deterministic CLI for rollout discovery, Git inspection, model-catalog loading, and validation; do not duplicate its logic or pass plan/prompt bodies through launcher arguments.

Use rollout evidence for the native collaboration mode; never infer mode from user prose:

- `plan`: explain that the user must press `Shift+Tab` once to enter Default mode, then stop.
- missing or unknown: stop and identify the missing/unsupported mode evidence with an actionable diagnostic.
- `default`: continue.

Require a valid approved plan with its exact text, title/preview, and SHA-256, plus a valid current model catalog. A nonzero preflight result is not permission to guess: continue only when the parsed evidence supports the proposal.

## One combined proposal

Render one complete proposal before asking for confirmation. Include:

- source thread;
- plan title, concise preview, and SHA-256;
- exact working directory;
- repository root, branch, HEAD, Git status, and baseline fingerprint;
- a dirty warning when Git is dirty;
- selected context mode;
- selected model and reasoning effort;
- one-line recommendation rationale;
- every preflight warning;
- concise manual alternatives derived only from the current catalog.

Default context to `plan`: a clean execution session containing the explicit handoff and approved plan, without the inherited Sol transcript. Offer `fork` only as an opt-in and explain that it creates a distinct execution thread with the full visible Sol history and its associated context cost. Never concurrently `resume` the open Sol thread.

Select the automatic model/effort recommendation using [model-selection.md](model-selection.md). Recommendations may appear in the proposal; require explicit confirmation before dispatching, spawning, or applying a selection or escalation. Show the exact selected pair and make every manual change explicit. A pair is selectable only when the current catalog supports it; never invent catalog entries.

## Confirmation and dispatch

After the proposal, stop and wait for a later response:

- Approve: launch exactly the rendered proposal.
- Edit: update the requested context or catalog-supported model/effort, rerun preflight as needed, render a fresh complete proposal, and require confirmation again.
- Reject: stop without launching.
- Unsupported choice: explain that the current catalog does not support it and stop without launching.

On approval, invoke the absolute launcher with the exact confirmed values:

```text
/home/jacob/.local/bin/codex-flow launch --thread "$SOURCE_THREAD" --cwd "$EXACT_CWD" --model "$MODEL" --effort "$EFFORT" --plan-sha256 "$PLAN_SHA256" --baseline-fingerprint "$BASELINE_FINGERPRINT" --context "$CONTEXT" --json
```

When Git is dirty, add `--confirm-dirty "$CONFIRMED_BASELINE_FINGERPRINT"`; omit it otherwise. Pass `--context plan` or `--context fork` exactly as confirmed. Never put plan or prompt bodies in launcher arguments; the existing launcher owns artifact creation and argv-oriented child boundaries.

The launcher reruns preflight. If plan text/hash, catalog support, native mode, or repository fingerprint is stale, do not retry or silently update the selection. Rerun preflight, render a refreshed complete proposal, and request confirmation again. After successful dispatch, report the returned run ID and artifact paths. Do not wait for the execution agent or claim execution completion.
