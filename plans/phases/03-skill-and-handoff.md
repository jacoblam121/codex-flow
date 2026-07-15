# Phase 03: Skill and Handoff UX

## Outcome

Make the proven launcher usable from the persistent Sol thread through a concise `$codex-flow handoff` skill workflow. This phase covers the
core model/context selection and confirmation experience, not subagent routing.

## Prerequisites

- Phase 02 is accepted and the CLI can launch both supported context modes directly.
- The official skill-creator assets and validator are available.

## In Scope

- Initialize a repository-owned `codex-flow` skill with the official skill initializer, then replace all placeholders.
- Keep `SKILL.md` concise and put detailed policies in directly linked references:
  - Handoff and native-mode boundary workflow.
  - Execution model recommendation and escalation policy.
  - Report and audit output contracts needed by later phases.
- Generate matching recommended `agents/openai.yaml` metadata; it remains optional Codex UI metadata inside the skill directory.
- Implement `$codex-flow handoff` behavior:
  - Run deterministic preflight against the invoking root thread.
  - Refuse launch when the latest rollout turn says native Plan mode is active and explain the single Shift+Tab boundary.
  - If mode evidence is absent or unsupported, stop with an actionable message rather than relying on user prose.
  - In Default mode, show one combined menu for context and model/effort.
  - Recommend the lowest adequate execution frontier choice with a one-line rationale.
  - Populate manual alternatives from the current model catalog without adding them to the automatic frontier.
  - Show the dirty-status warning and exact plan preview/hash.
  - Call the absolute launcher path only after explicit confirmation.
- State the host boundary plainly: the skill can launch another TUI but cannot change the model or mode of the currently running Sol TUI.
- Include the run marker and best-effort versioned report/audit instructions in generated handoffs, while stating that live diff/tests are the
  review authority.
- Provide an explicitly approved, reversible development link for the CLI and skill so a fresh Codex session can forward-test discovery. Do not
  implement the final installer, global `AGENTS.md`, personal roles, or approval rule here.

## Contracts

- Implicit skill activation may explain the workflow, but only an explicit user handoff/launch request may open a new terminal.
- Plan-only remains the default and starts a clean new execution session with no inherited source transcript; the approved plan and handoff are
  its explicit context.
- Sol fork is opt-in and creates a distinct execution thread containing the full visible source history; the confirmation must make that
  inherited context and its associated context cost explicit.
- One combined user confirmation covers plan hash, context mode, execution model/effort, repository baseline, and dirty-state fingerprint.
- Native mode detection comes from the exact rollout characterized in Phases 00-01, not from parsing the user's words.
- Model recommendations are advisory until confirmed; no model or effort changes silently.
- Report/audit formatting is a behavioral request with a degraded fallback, not a guarantee that the model will emit valid structure.

## Tests

- Official skill validation and generated metadata consistency.
- Trigger prompts for explicit handoff, explanatory questions, ordinary coding, and unrelated tasks.
- Plan-mode refusal, unknown-mode refusal, and Default-mode launch path.
- Execution-model recommendations at every automatic frontier choice plus catalog-derived manual choices.
- Combined confirmation approval, edit, rejection, stale fingerprint, and unsupported model flows.
- Development link, repeat link, and removal without damaging unrelated user files.
- One approved fresh-session forward test that discovers the skill and reaches the launcher confirmation without launching unexpectedly.

## Exit Criteria

- `$codex-flow handoff` launches the exact confirmed selection and never launches from native Plan mode or unknown mode.
- The skill cannot cause a terminal launch from implicit activation alone.
- A fresh session discovers the development-linked skill and its metadata.
- The run handoff contains the exact plan, run marker, preservation/validation constraints, and best-effort report contract.
- The skill validator and phase tests pass.

## Explicitly Deferred

- Personal subagent roles, global routing guidance, and explicit per-spawn model/effort selection (Phase 06).
- Automated execution-report recovery and Sol audit.
- Repair handoffs.
- Final install/uninstall, approval-rule installation, and conflict handling.
- Grounded Markdown plan bundles.

## Required Executor Report

Report skill files and references, temporary development links, validation commands, trigger-test results, representative handoff decisions,
fresh-session observations, and any native-mode or skill-discovery limitation.
