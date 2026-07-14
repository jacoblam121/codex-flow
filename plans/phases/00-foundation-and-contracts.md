# Phase 00: Foundation, Contracts, and Compatibility Baseline

## Outcome

First characterize the installed Codex/WSL/Windows Terminal surfaces that the core workflow depends on, then create a runnable, testable Python
project with stable internal contracts. Later phases must extend these contracts rather than inventing parallel representations.

## Prerequisites

- The master plan and `index.md` are accepted as authoritative.
- Python 3.12 or newer is available.
- No existing implementation needs compatibility support.

## Planning Evidence to Reconfirm

As of 2026-07-12 on the target machine:

- Codex CLI `0.144.1` exposes `codex fork [SESSION_ID] [PROMPT]`, model/config overrides, and parseable
  `codex debug models --bundled` JSON.
- The root tool subprocess receives `CODEX_THREAD_ID`, and it matches the exact root rollout metadata/filename.
- The root rollout records Plan/Default in `turn_context.payload.collaboration_mode.mode`; its completed structured `Plan` item and tagged final
  answer remain intact after the switch to Default and later Default-mode turns.
- Official Codex documentation describes `fork` as creating a new task while preserving the original transcript, and official Rules
  documentation defines literal argv-prefix rules. Fork gets an ordinary target-version smoke; Rules and model-debug surfaces remain
  experimental compatibility points.
- Microsoft documents Windows Terminal window selectors `last` and `0` as equivalent most-recent-window aliases.
- The current model-visible `spawn_agent` schema hides per-spawn role/model/effort metadata even though the binary supports it internally; Phase
  06 owns the isolated compatibility gate for the current-build switch.

## In Scope

- Before freezing schemas or CLI contracts, record a concise compatibility matrix for the target machine:
  - Installed Codex version and exact `fork` and `debug models --bundled` help/output shapes.
  - Root `CODEX_THREAD_ID` equality with the source rollout's session metadata; characterize and reject subagent-source sessions for handoff.
  - Latest `turn_context.payload.collaboration_mode.mode` values for Plan and Default turns.
  - Persistence after Plan -> Default of both the completed structured `Plan` item and complete tagged final-answer fallback.
  - Windows Terminal's documented `last`/`0` most-recent-window behavior and availability of direct `wt.exe`/`wsl.exe --exec` invocation.
  - Exact argv-prefix approval-rule syntax and its experimental status.
- Keep the matrix in the executor report and capture only small sanitized rollout/catalog fixtures needed by later tests. Do not build a general
  probe framework.
- Classify failures before continuing:
  - Missing exact root thread/rollout or plan/mode evidence blocks the core and requires a plan revision.
  - Missing fork support removes fork from v1 but does not block plan-only handoff.
  - Missing bundled model discovery uses an actionable compatibility error or a user-approved explicit model; it does not justify guessing.
  - Per-spawn subagent metadata is deliberately gated in Phase 06 and does not block the core handoff workflow.
- Create `pyproject.toml`, a `src/codex_flow/` package, `tests/`, and a thin development entry point.
- Use only the Python standard library at runtime. Configure `pytest` as development-only test tooling.
- Implement the CLI dispatcher and help for these eventual commands:
  - `doctor`
  - `preflight`
  - `launch`
  - `show`
  - `install`
  - `uninstall`
  - internal `child`
- Implement shared path resolution:
  - `CODEX_HOME`, defaulting to `~/.codex`.
  - `XDG_STATE_HOME`, defaulting to `~/.local/state`.
  - Codex Flow run storage at `<state-home>/codex-flow/runs`.
- Implement versioned dataclasses and JSON serialization for:
  - Run identity and lineage.
  - Source and execution thread references.
  - Repository and Git baseline metadata.
  - Handoff context, model, and reasoning selection.
  - Artifact paths and timestamps.
- Implement atomic JSON writes using a temporary sibling file followed by `os.replace`.
- Define typed application errors and stable exit behavior:
  - `0`: success.
  - `2`: invalid CLI usage.
  - `3`: failed precondition or missing required state.
  - `4`: unsupported or unavailable environment capability.
  - `5`: external command failure.

## Contracts

- Use UUIDv4 strings for run IDs and validate them before using them in paths or cross-boundary commands.
- Start manifests at `schema_version: 1`; reject unsupported future versions rather than guessing.
- Store absolute normalized paths in manifests while preserving original user-facing paths where useful for messages.
- Serialize timestamps as UTC RFC 3339 strings ending in `Z`.
- Never store prompt or plan text directly in shell command fields. Store artifact paths instead.
- Keep CLI presentation separate from domain logic so tests can exercise behavior without a terminal.

## Tests

- CLI help and unknown-command behavior.
- Sanitized compatibility fixtures and the expected failure branch for each core capability.
- XDG and Codex home resolution with environment overrides.
- Run-ID validation, including traversal and shell-metacharacter attempts.
- Manifest round-trip and unsupported schema rejection.
- Atomic-write success and cleanup after a simulated replacement failure.
- Exit-code mapping for each application-error category.

## Exit Criteria

- `python -m codex_flow --help` and the development entry point produce the same command list.
- `pytest` passes without accessing the network, Codex sessions, Git, or Windows executables.
- A manifest fixture round-trips without losing fields.
- No command except the explicitly tested atomic-write helper mutates external user state.
- The compatibility matrix distinguishes verified current behavior, experimental interfaces, and unresolved live-smoke checks; Phase 01 does not
  have to rediscover the target record shapes.

## Explicitly Deferred

- Rollout parsing and Git inspection.
- Model-catalog discovery.
- Run creation and terminal launching.
- Skill, agent, rule, or global instruction installation.
- Live fork/terminal smoke tests and explicit per-spawn subagent model/effort verification.
- Grounded Markdown plan bundles.

## Required Executor Report

Report the compatibility matrix and evidence, any v1 capability removed by a failed check, package layout, contracts introduced, commands
exercised, test output, deviations, and any contract question that later phases must resolve.
