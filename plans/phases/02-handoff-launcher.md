# Phase 02: Handoff Launcher

## Outcome

Launch an interactive execution Codex session with an explicit model and effort in a new Windows Terminal tab while leaving the source Sol TUI
alive. Support both clean plan-only context and a fork of the source thread.

## Prerequisites

- Phase 01 is accepted.
- The WSL2 environment exposes `WSL_DISTRO_NAME`, `WT_PROFILE_ID`, `wsl.exe`, and a directly callable Windows Terminal executable.

## In Scope

- Implement `codex-flow launch` with explicit arguments for source thread, CWD, context mode, model, effort, and confirmed baseline fingerprint.
- Re-run preflight immediately before launch and abort if its fingerprint differs from the confirmed fingerprint.
- If Git is dirty, require an explicit confirmation value tied to that exact fingerprint. Do not enforce a writer lock.
- Create `<state-home>/codex-flow/runs/<run-id>/` containing:
  - Immutable `manifest.json` launch facts.
  - Exact `plan.md`.
  - Generated `handoff.md`.
  - Reserved paths for later `execution.json`, `report.json`, and `audit.json` sidecars; do not create empty success-looking sidecars.
- Build the handoff contract from the approved plan plus run ID, repository metadata, preservation guardrails, validation expectations, and the
  best-effort structured completion-report request with an unstructured fallback.
- Implement context modes:
  - `plan`: start a new `codex` TUI with the handoff content.
  - `fork`: run `codex fork <source-thread-id>` with a concise execution instruction and explicit selected model/effort.
- Implement internal `codex-flow child <run-id>`:
  - Read and validate the manifest.
  - Change to the recorded CWD.
  - Construct the Linux Codex argv without a shell.
  - Replace itself with the interactive Codex process.
- Resolve the child executable deliberately:
  - During development, use the absolute Phase 00 development entry point; do not assume the Phase 07 `~/.local/bin` link already exists.
  - After installation, use the fixed absolute installed shim.
  - Treat this as trusted launcher configuration, not user-authored per-run data.
- Open a tab in the most-recent Windows Terminal window, using the current profile and WSL distribution.
  - Prefer direct argv construction for `wt.exe -w last new-tab ... wsl.exe --exec ...`; `last` and `0` are documented aliases.
  - The fixed/resolved child executable and validated run ID are the only Linux command tokens crossing the boundary. Never pass plan, prompt,
    target CWD, model, or other user-authored text.
  - Do not introduce a CMD or shell layer unless direct invocation fails on the target and a separately reviewed fallback is added.
- Implement `--dry-run --json` showing sanitized Windows and Linux argv without launching or creating a persistent run.
- When Windows Terminal is unavailable, print the exact safe Linux child command for manual use and return the unsupported-environment code.

## Contracts

- Model and reasoning effort are always explicit on execution Codex invocations.
- The initial execution prompt contains a unique machine-readable run marker.
- Plan-only is the default context mode; fork must be an explicit selection.
- Same-thread live resume is not supported.
- The launch manifest is immutable. Later phases write discovered execution metadata and recovered semantic artifacts to separate atomic sidecars.
- Failed launch attempts retain enough state for diagnosis and must not be presented as successfully started.

## Tests

- Plan-only and fork Linux argv construction.
- Windows Terminal/WSL argv serialization, including a resolved child executable path containing spaces; no shell expansion is involved.
- Plans containing spaces, ampersands, quotes, Unicode, and large content never appear in the Windows argv.
- Run-ID and manifest-path traversal attempts.
- Baseline changing between preflight and launch.
- Clean and confirmed-dirty launches.
- Missing Terminal, WSL, profile, distribution, or Codex executable.
- External command failure and useful diagnostics.
- Dry-run output proves that no plan or CWD crosses the Windows boundary.

## Exit Criteria

- Automated dry-run tests pass for plan-only and fork.
- One approved manual smoke test opens Luna in a new Ubuntu tab at the exact CWD while Sol remains responsive.
- One approved fork smoke test proves the child has a distinct thread ID, retains a known planning-context fact, honors the selected model/effort,
  and leaves the source Sol thread usable.
- The child TUI reports the requested model and reasoning effort.
- The run directory contains exact, inspectable plan and handoff artifacts.
- No shell parses user-authored plan, target path, model, or prompt data.

## Explicitly Deferred

- Conversational menus and skill activation.
- Subagent routing and personal agent roles.
- Retrieval of the execution report.
- Review and repair workflows.
- Grounded Markdown plan bundles.

## Required Executor Report

Report the exact argv shapes, state artifacts, automated results, manual smoke result if authorized, launch failures, and any environment-specific
assumption.
