# Phase 06: Capability-Gated Delegation Routing

## Outcome

Add four useful personal subagent roles and an instruction-driven batch approval workflow that can pass the user's confirmed model and reasoning
effort explicitly on every fresh-context spawn. Keep the core handoff/review/repair workflow independent of this experimental integration.

## Prerequisites

- Phases 00 through 05 are accepted.
- The user approves a small fresh-session subagent probe and any temporary development links needed for it.
- The installed Codex version still has multi-agent support and the runtime model catalog contains the requested selections.

## Capability Gate

Before creating global routing claims:

1. Start a disposable fresh Codex session with the intended current-build configuration:

   ```toml
   [features.multi_agent_v2]
   enabled = true
   hide_spawn_agent_metadata = false
   ```

2. Confirm the model-visible fresh-context spawn schema exposes `agent_type`, `model`, and `reasoning_effort`.
3. Spawn one harmless read-only child with no history inheritance and inspect its rollout/session metadata to prove the selected role, model, and
   effort were honored.
4. Record the Codex version, configuration, schema observation, and child evidence in the executor report.

This configuration is an internal/current-build compatibility switch, not a documented stable public interface. Do not install it silently. If
the fields are absent or ignored, stop this phase with an explicit limitation: do not create a role-by-model matrix, do not claim selectable
routing works, and do not silently spawn on the inherited Sol model.

## In Scope

- Create model-neutral, read-only personal agent definitions for:
  - `researcher`: causal and architectural investigation.
  - `explorer`: targeted repository, symbol, and entry-point discovery.
  - `reviewer`: correctness, security, regression, and test-gap review.
  - `verifier`: external documentation, API, and version verification.
- Keep semantic roles separate from cost/capability by omitting model and effort fields from their TOMLs.
- Encode only this automatic recommendation ladder:
  - Luna low.
  - Luna medium.
  - Luna xhigh.
  - Luna max.
  - Sol high.
  - Sol max.
- Populate all manual alternatives from the current model catalog. Luna high, other Sol efforts, Sol ultra, and Terra remain manual-only and are
  never automatically recommended.
- Add concise skill references for:
  - Role choice.
  - Lowest-adequate-rung recommendation.
  - Batch manifest approval and row edits.
  - Explicit escalation after an insufficient result.
- Before each proposed spawn batch, instruct the parent to show task, role, recommended model/effort, rationale, and bounded context strategy.
  Accept whole-batch approval or row edits; do not spawn before approval.
- Spawn only fresh-context children with self-contained prompts and explicit approved `agent_type`, `model`, and `reasoning_effort`. Current
  Codex does not permit model/effort overrides on full-history child forks.
- Add repository templates for the four personal TOMLs and a compact managed block for global `~/.codex/AGENTS.md` that tells normal sessions
  to use this workflow before delegation. Phase 07 owns global installation.
- If results are insufficient, recommend the next Pareto rung and request approval again; never escalate or respawn silently.

## Contracts

- The batch manifest and global trigger are behavioral guidance for a personal workflow, not a mechanical hook or security boundary.
- Higher-priority host instructions and unavailable tool fields can prevent the policy from applying; the skill must report that honestly.
- Role files define behavior, not model cost or capability.
- Batch approval applies even to one proposed subagent.
- Every routed spawn uses `fork_turns = "none"` (or the current equivalent for a fresh context) and a self-contained task prompt.
- When explicit selection is unavailable, default to cancel and explain the limitation. An inherited-model spawn requires a separate explicit user
  choice and is never represented as compliant routing.

## Tests

- Static validation of all four agent TOMLs.
- Capability-gate schema visibility and effective child role/model/effort.
- Model recommendations at every automatic rung plus catalog-derived manual-only choices.
- Batch approval, row edit, rejection, and explicit escalation flows.
- Fresh-context prompt completeness and rejection of a model override combined with a full-history fork.
- Trigger prompts for investigation, exploration, review, documentation verification, ordinary coding, and unrelated tasks.
- Forward-tests showing the guidance usually produces the manifest before spawning, without claiming hard enforcement.

## Exit Criteria

- A fresh-session probe proves explicit role/model/effort selection is visible and honored on the target Codex build.
- Approved spawn calls contain the exact role, model, reasoning effort, and fresh-context strategy shown in the manifest.
- A Sol ultra planning prompt follows the manifest workflow in representative forward-tests and does not silently inherit Sol for approved Luna
  work.
- Manual-only models never appear as automatic recommendations.
- Failed or insufficient work returns to the parent for a newly approved rung rather than escalating automatically.
- The skill and role validations pass with no role-by-model file multiplication.

## Explicitly Deferred

- Mechanical interception of every possible subagent spawn.
- A supported hook/policy enforcement layer if Codex later exposes one.
- Automatic editing of undocumented Codex feature configuration.
- Recursive subagent delegation and full-history cross-model children.
- Grounded Markdown plan bundles.

## Required Executor Report

Report the capability-gate evidence, exact temporary configuration, role files, representative recommendation/manifests, spawn metadata and child
observations, forward-test limitations, validation commands, and whether selectable routing can be enabled safely on this Codex version.
