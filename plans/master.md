  # Codex Flow: Persistent Sol Planning and Luna Execution

  ## Summary

  Build a user-scoped $codex-flow skill plus a deterministic Python launcher for WSL2 and Windows Terminal.

  Normal workflow:

  1. Start codex normally and plan with Sol in native Plan mode.
  2. Approve the final plan.
  3. Press Shift+Tab once to enter Default mode.
  4. Invoke $codex-flow handoff, choose context and execution model.
  5. Launch Luna in a new tab while Sol remains open as the control/review thread.
  6. Invoke $codex-flow review to retrieve Luna’s available execution result/report and audit its actual changes.
  7. Invoke $codex-flow repair to launch a fresh repair, fork Luna’s context, or let Sol fix it.

  Do not change the global model defaults. The existing plan_mode_reasoning_effort = "max" already makes native planning use Sol max; Sol
  ultra remains selectable through /model.

  ## Delivery Phases

  Implement the core workflow through the bounded handoffs in [phases/index.md](phases/index.md). Each phase must satisfy its own exit
  criteria before the next dependent phase begins. Persisted, phase-aware plan bundles are intentionally deferred and specified separately in
  [deferred/grounded-plan-bundles.md](deferred/grounded-plan-bundles.md).

  ## User-Facing Interfaces

  - $codex-flow handoff
      - Find the exact source rollout using CODEX_THREAD_ID.
      - Prefer the latest structured completed Plan item, cross-check it against the matching final <proposed_plan>, and retain the tagged final
        answer as a compatibility fallback.
      - Show a combined confirmation menu containing:
          - plan-only clean context, recommended.
          - fork of the Sol thread with full planning context.
          - Recommended model/effort, rationale, and manually selectable alternatives.
          - Git branch, HEAD, working directory, and dirty-status warning.

      - Require explicit confirmation before calling the launcher.

  - $codex-flow review
      - Select the latest unreviewed run associated with the current Sol thread and repository; show a picker when ambiguous.
      - Retrieve Luna’s structured report when present; otherwise use the exact run's latest assistant result as unstructured context.
      - Independently inspect the live status, diff, tests, deviations, and unresolved risks.
      - Produce a run-linked audit that can be consumed by repair.

  - $codex-flow repair
      - Always offer:
          - Fresh linked execution context, recommended by default.
          - A new tab forked from the previous Luna thread.
          - Fix directly in the current Sol thread.

      - Include the original plan, previous structured report or labeled unstructured result, Sol audit findings, and current repository state.
      - Re-run the model recommendation and confirmation menu.
      - Before Sol fixes directly, require confirmation that no Luna turn is still editing the shared worktree.

  - codex-flow doctor, preflight, and show provide deterministic diagnostics and read-only run inspection.

  Live same-thread resume is excluded while Sol remains open. For an older closed planning session, resume it normally and invoke $codex-flow
  from that session.

  ## Implementation

  - Install the skill under ~/.agents/skills/codex-flow/, with its Python scripts, workflow references, and recommended optional
    agents/openai.yaml metadata bundled alongside SKILL.md. This is Codex’s documented user-skill location and structure. Codex skill
    documentation (https://developers.openai.com/codex/skills)

  - Install an executable shim at ~/.local/bin/codex-flow; use only Python’s standard library.
  - Store run data outside repositories under ~/.local/state/codex-flow/runs/<run-id>/, including:
      - Source and execution thread IDs.
      - Exact approved plan and plan hash.
      - Parent run for repairs.
      - Context mode, model, and reasoning effort.
      - CWD, repository root, branch, HEAD, and dirty baseline.
      - Generated handoff prompt.

    Keep launch facts in an immutable manifest. Store discovered execution-thread metadata and recovered report/audit data in separate atomic
    sidecars rather than mutating the launch record.

  - Never pass plan, prompt, target CWD, or model text through Windows Terminal. Apart from the fixed/resolved launcher command, the validated
    run ID is the only dynamic child token crossing the boundary; the WSL child reads the handoff locally and invokes Codex with an argv array.

  - Target the most-recent Terminal window with wt.exe -w last new-tab (`last` and `0` are documented aliases), reuse WT_PROFILE_ID, select
    WSL_DISTRO_NAME, and start the child in the recorded CWD. Prefer direct argv-based wt.exe -> wsl.exe --exec invocation from WSL; do not add
    a CMD layer unless the target machine proves it necessary. Windows Terminal command-line arguments
    (https://learn.microsoft.com/windows/terminal/command-line-arguments)

  - Launch plan-only runs with explicit codex -C … -m … -c model_reasoning_effort=…; launch context-preserving runs through codex fork.
  - Ask Luna to end completed, partial, and blocked runs with a machine-locatable <codex_flow_report run_id="…"> containing versioned JSON for:
      - Status and summary.
      - Files changed.
      - Commands/tests and outcomes.
      - Plan deviations.
      - Remaining issues and recommended follow-up.

  - Treat report and audit envelopes as best-effort transport, never as proof of correctness or task completion. Extract them lazily from the
    exact rollout; if a marker is missing or malformed, warn Sol, retain the latest assistant result as context, and continue with a live
    repository-based review.
  - Add a narrow allow rule only for /home/jacob/.local/bin/codex-flow launch; all menus and dirty-worktree confirmation remain mandatory.
  - Add a compact ~/.codex/AGENTS.md trigger instructing Codex to use the skill’s routing policy before subagent spawns. This is behavioral
    guidance, not a mechanical interception or security boundary. Codex loads this global file for every session. Codex AGENTS.md
    documentation (https://developers.openai.com/codex/guides/agents-md)

  - Warn—but do not block or lock—when Git is dirty. Support non-Git directories with a reduced audit warning.

  ## Subagent Routing

  Create model-neutral, read-only personal roles under ~/.codex/agents/:

  - researcher: causal and architectural investigation.
  - explorer: targeted repository, symbol, and entry-point discovery.
  - reviewer: correctness, security, regressions, and test gaps.
  - verifier: external documentation, API, and version claims.

  Omitting model fields keeps role behavior separate from per-batch model selection. On the current Codex build, explicit per-spawn role/model/
  effort fields are hidden by default and must be exposed and verified in a fresh session before this routing feature is enabled. Keep this as
  a capability-gated, experimental integration; if explicit fields are unavailable, do not silently inherit Sol's model and do not generate a
  role-by-model matrix. Codex subagent documentation (https://developers.openai.com/codex/subagents)

  Use this exact recommendation ladder:

  | Rung | Typical recommendation |
  | --- | --- |
  | Luna low | Mechanical lookup or trivial validation |
  | Luna medium | Bounded exploration or documentation extraction |
  | Luna xhigh | Cross-file exploration or moderate synthesis |
  | Luna max | Broad code audit, correctness analysis, or execution verification |
  | Sol high | Ambiguous causal or architectural investigation |
  | Sol max | High-risk global synthesis or escalation after Luna proves insufficient |

  Encode only the six automatic recommendation rungs. Populate Luna high, other Sol efforts, Sol ultra, Terra, and any other manual choices
  from the current model catalog; they remain manually selectable but are never automatically recommended.

  Before every spawn batch, present a manifest containing task, role, recommended model/effort, and rationale. Accept whole-batch approval or
  row edits. Spawn with explicit model and effort only after approval, using self-contained prompts rather than full-history inheritance. If
  results are insufficient, recommend the next rung and request approval again; never escalate silently. This is an instruction-driven personal
  workflow and must be forward-tested, not described as hard enforcement.

  ## Test Plan and Defaults

  - Characterize the installed Codex version before freezing parser/launcher contracts, and retain fixtures for structured Plan items, tagged
    plan fallbacks, mode records, and root/subagent collisions.
  - Unit-test rollout parsing with root/subagent collisions, multiple plans, malformed records, missing reports, and multiple linked repairs.
  - Test model validation, run-ID validation, paths containing spaces, prompt injection resistance, and Windows/WSL argv serialization.
  - Add dry-run tests for plan-only, Sol fork, Luna-context repair fork, and manual fallback when Windows Terminal is unavailable.
  - Verify dirty and non-Git warnings without blocking launch.
  - Smoke-test that a Luna tab opens in Ubuntu at the exact CWD with the selected model/effort while Sol remains usable.
  - Verify review retrieves the correct report and handles completed, partial, blocked, and missing-report runs.
  - Validate the skill metadata, four agent TOMLs, global trigger, and narrow approval rule. Separately prove in a fresh session that explicit
    per-spawn role/model/effort fields are visible and honored before accepting delegation routing.
  - Default to plan-only handoff, a shared worktree without writer locks, latest unreviewed-run selection, and the lowest adequate Pareto-
    ladder rung.
