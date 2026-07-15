# Phase 07: Personal Installation and End-to-End Validation

## Outcome

Deliver a simple, idempotent, reversible personal installation and demonstrate the complete Sol-to-execution-agent-to-Sol workflow in the target WSL2
environment. Keep installation conservative: own dedicated paths, refuse conflicts, and avoid a general configuration-management system.

## Prerequisites

- Phases 00 through 05 are accepted. Phase 06 is either accepted or explicitly unavailable/skipped because the target Codex build cannot expose
  and honor per-spawn metadata.
- The user approves writes to personal Codex configuration paths and any live Windows Terminal/subagent forward-tests.

## In Scope

- Finish `codex-flow install` and `uninstall` for personal use:
  - Preflight every destination before changing any of them.
  - Symlink the repository CLI into `~/.local/bin`.
  - Symlink the complete skill directory, including `agents/openai.yaml`, into the documented personal skill directory.
  - When Phase 06 is enabled, symlink the four personal agent TOMLs and install its global routing block; otherwise install only the core
    handoff/review/repair assets and report routing as unavailable.
  - Install a dedicated `codex-flow.rules` file containing an exact absolute argv-prefix rule for `codex-flow launch`, with positive and negative
    inline match examples.
  - Add a uniquely delimited compact managed block to global `AGENTS.md` while preserving all user content only when routing is enabled.
  - Refuse conflicting non-owned destinations and explain the manual resolution; do not rename or back up user files automatically.
- Make repeat install a no-op when every owned target and managed block already matches.
- Make uninstall remove only symlinks that still target this repository, the dedicated unchanged rule, and the exact managed block. Warn and
  preserve anything modified or no longer provably owned.
- When routing is enabled, keep the current-build subagent metadata setting manual and explicit. Print the exact Phase 06 snippet and restart
  requirement when missing; `doctor` verifies it but the installer does not rewrite general `config.toml`.
- Implement a focused `codex-flow doctor` with pass/warn/fail checks for actual workflow blockers:
  - Codex command/version and the characterized `fork`/model-catalog surfaces.
  - Live root thread ID, rollout/mode readability, and state-directory writability when invoked inside a session.
  - WSL distribution, direct `wt.exe`, `wsl.exe`, and current Terminal profile.
  - Installed CLI/skill/roles/global trigger/rule links.
  - Explicit subagent metadata visibility prerequisite when delegation routing is enabled.
- Keep run storage private with a `0700` run root and owner-only artifact files. Continue atomic sidecar writes; no locking subsystem is needed.
- Do not print plan or handoff bodies in routine logs/errors. Explicit `show` output may display them only when the user asks.
- Add concise repository-level usage and development documentation. Do not add auxiliary README/install files inside the skill bundle itself.
- Forward-test the installed skill in fresh threads using raw tasks, without leaking expected outputs. Request approval before tests that launch
  costly agents or modify live projects.

## End-to-End Scenarios

1. Sol max Plan mode produces an approved plan; Default-mode handoff launches a confirmed execution-agent plan-only run; the execution report is
   recovered when present; Sol independently reviews the live diff/tests.
2. A Sol fork handoff opens a distinct execution thread with retained planning context and explicit model/effort while the source remains usable.
3. A dirty-repository warning is tied to the exact fingerprint; after confirmation, review distinguishes baseline changes from execution changes.
4. A missing/malformed execution report falls back to the exact unstructured result and repository-only review.
5. Sol launches a fresh linked execution repair, reviews it, then exercises an execution-context fork without opening the same session twice.
6. Sol-fix requires confirmation that no execution editing turn is active in the shared worktree.
7. When Phase 06 is enabled, Sol proposes a mixed subagent batch; the user edits one row; only the approved explicit fresh-context selections
   spawn.
8. Windows Terminal is unavailable and Codex Flow prints a safe manual child command without losing the run plan.
9. Install, repeat install, doctor, uninstall, and reinstall preserve unrelated global configuration.

## Tests

- Full automated suite from a clean checkout.
- Install/reinstall/uninstall tests in an isolated fake home, including conflicts and user-modified managed artifacts.
- Managed-block merge/removal with existing global instructions.
- Symlink ownership and dedicated-rule matching behavior.
- Private state permissions and routine-output privacy checks.
- One graceful non-Git warning path; do not multiply non-Git cases across every workflow test.
- Approved WSL/Windows Terminal smoke tests with recorded evidence.
- Approved fresh-thread skill, routing, report-fallback, and repair forward-tests.

## Exit Criteria

- Every automated test passes from a clean checkout with no network requirement.
- `doctor` gives actionable pass/warn/fail results for core blockers and clearly labels the experimental routing prerequisite.
- All approved end-to-end scenarios pass or have a specifically accepted platform limitation.
- Uninstall removes only provably owned artifacts and leaves unrelated configuration byte-for-byte intact.
- Private run storage, atomic JSON replacement, and no-routine-prompt-logging remain intact without locks or a redaction subsystem.
- The core release is complete without implementing `../deferred/grounded-plan-bundles.md`.

## Explicitly Deferred

- Automatic backup/replacement of conflicting user files.
- General transactional configuration management or migration machinery.
- Performance telemetry and a general log-redaction engine.
- Automatic editing of undocumented Codex feature configuration.
- Grounded Markdown plan bundles.

## Required Executor Report

Report install destinations and ownership rules, automated results, each approved live scenario, doctor findings, forward-test observations, known
limitations, preserved conflicts, and the exact deferred items remaining after core acceptance.
