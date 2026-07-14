# Codex Flow Core Delivery Phases

## Purpose

Turn the master plan into bounded, independently reviewable implementation handoffs. A phase is complete only when its tests and exit criteria
pass; completing code without the required evidence does not complete the phase.

The grounded-plan-bundle feature in `../deferred/grounded-plan-bundles.md` is not part of these phases.

## Sequence

| Phase | Outcome | Depends on |
| --- | --- | --- |
| [00 — Foundation, contracts, and compatibility](00-foundation-and-contracts.md) | Characterized target capabilities plus a runnable Python package, CLI skeleton, schemas, and test harness | None |
| [01 — Session and preflight core](01-session-and-preflight.md) | Exact rollout discovery, approved-plan extraction, Git preflight, and model validation | 00 |
| [02 — Handoff launcher](02-handoff-launcher.md) | Plan-only and Sol-fork execution tabs launch safely in WSL/Windows Terminal | 01 |
| [03 — Skill and handoff UX](03-skill-and-handoff.md) | `$codex-flow handoff` and the minimal discoverable skill workflow | 02 |
| [04 — Reporting and review](04-reporting-and-review.md) | Exact execution evidence is associated and Sol audits the live implementation | 03 |
| [05 — Repair and run lineage](05-repair-and-lineage.md) | Fresh repair, Luna-context fork, and Sol-fix paths work from an audit | 04 |
| [06 — Delegation routing](06-delegation-routing.md) | Capability-gated custom roles, batch approval, and explicit Pareto model routing | 05 |
| [07 — Installation and validation](07-installation-and-validation.md) | Idempotent personal installation and end-to-end validation | 05; 06 when routing is enabled |

## Shared Constraints

- Use Python 3.12 or newer and Python's standard library at runtime. Development-only test tooling may use `pytest`.
- Keep shell parsing away from plans and prompts. Pass Linux arguments as argv arrays; apart from the fixed/resolved child command, send no
  per-run dynamic data except a validated run ID across the Windows Terminal boundary.
- Preserve existing user files and configuration. Installation must use managed blocks, dedicated files, or symlinks and must be reversible.
- Never launch a handoff, spawn subagents, escalate a model, or accept dirty Git state without the confirmation required by the master plan.
- Keep the source Sol thread open. Do not implement concurrent live `resume` of the source thread.
- Treat rollout JSONL as a versioned external format: parse defensively, ignore unknown records, and fail with actionable errors when required
  records are absent.
- Keep operational state in the XDG state directory, never in the target repository.
- Treat model-emitted report/audit envelopes and skill/AGENTS routing instructions as useful behavioral interfaces, not security or correctness
  boundaries. Live repository evidence remains authoritative.
- Do not silently fall back to inherited parent settings when explicit subagent role/model/effort selection is unavailable.
- Do not implement the deferred grounded-plan functionality while completing a core phase.

## Handoff Discipline

For each phase:

1. Give the executor only the master plan, the selected phase file, and relevant outputs from completed dependencies.
2. Require the executor to preserve unrelated and pre-existing changes.
3. Require a concise completion report listing changed files, validation commands, failures, deviations, and remaining risks.
4. Have Sol review the implementation against the phase exit criteria before starting the next phase.
5. If a phase exposes a contract flaw, revise the affected pending phase files rather than silently broadening the active handoff.

## Working Assumptions to Revisit Before Phase 00

- Repository code uses a `src/codex_flow/` package, `tests/`, `pyproject.toml`, and a thin `bin/codex-flow` development entry point.
- The runtime has no third-party Python dependencies; tests use the already-available `pytest` command.
- Phase 03 may use an explicitly approved temporary development link so a fresh session can discover the skill. Phase 07 owns the real install
  and uninstall commands. Global `AGENTS.md` uses a removable managed block because it cannot be replaced safely with a symlink.
- The first release targets this WSL2 Ubuntu and Windows Terminal environment, with a printed manual-launch fallback elsewhere.
