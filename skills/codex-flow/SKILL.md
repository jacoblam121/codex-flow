---
name: codex-flow
description: Prepare and confirm a Codex Flow handoff from the persistent Sol planning thread to a separate execution TUI. Use for an explicit `$codex-flow handoff`, a natural-language request to hand off an approved plan for execution, or an explanatory question about Codex Flow. Do not use for ordinary coding, planning unrelated to a handoff, or unrelated work.
---

# Codex Flow

Use this skill only for Codex Flow explanation or an approved-plan handoff.

## Explanation-only requests

Answer explanations exclusively from this canonical routing summary. Do not run commands or open bundled references when the user prohibits commands; never guess missing model information.

Use this exact automatic frontier, in order, with the lowest adequate supported choice:

These seven choices span six capability tiers.

1. `gpt-5.6-luna` / `low`: trivial, read-only, mechanical, or single-step work requiring essentially no synthesis.
2. `gpt-5.6-luna` / `medium`: bounded exploration, documentation extraction, narrow code reading, or small sanity checks; not the normal implementation default.
3. `gpt-5.6-luna` / `xhigh`: the default for ordinary implementation, bounded multi-file work, meaningful verification, and slightly complex subagent queries.
4. `gpt-5.6-luna` / `max`: short-horizon but difficult, well-specified work needing concentrated reasoning, dense debugging, or a focused audit with a bounded blast radius.
5. `gpt-5.6-sol` / `medium`: the Tier-4 peer of Luna max for long-horizon, multi-stage work involving broad context or many sequential exploration/edit/test cycles; prefer it when token efficiency justifies its greater monetary cost.
6. `gpt-5.6-sol` / `high`: complex, architecture-sensitive, correctness-critical, or technically unforgiving execution requiring deep causal reasoning, including subtle low-level/systems, concurrency, compiler/runtime, performance, memory-safety/security, or cross-component invariant work. Select it directly when inherent complexity or risk warrants it.
7. `gpt-5.6-sol` / `max`: the highest-risk or highest-uncertainty work, novel cross-system/global synthesis, or escalation after Sol high proves insufficient.

Luna max and Sol medium are Tier-4 peers, not sequential rungs. Capability and correctness risk take priority over horizon; horizon chooses between the Tier-4 peers only after Tier 4 is judged adequate. If Tier 4 is unnecessary, remain on Luna xhigh. If the Tier-4 horizon is unclear, prefer Luna max. Luna high, Sol low/xhigh/ultra, Terra, and other catalog entries are manual-only. Use only the exact model slugs and efforts listed here and in the current catalog; never invent, rename, modernize, or substitute model families from memory.

## Handoff requests

For an explanation, describe the workflow and boundaries without running commands. For an explicit handoff request, read [handoff.md](references/handoff.md), [model-selection.md](references/model-selection.md), and [evidence-contracts.md](references/evidence-contracts.md) completely before preflight. If a required reference cannot be read, stop with an actionable explanation rather than guessing. Follow the handoff reference: run preflight, render one complete proposal, and wait for a later plain-language confirmation before launching.

The skill may launch another execution TUI through the absolute Codex Flow launcher, but it cannot change the current TUI's model or native Plan/Default mode. Implicit activation may explain or prepare only; it must never launch. Require both explicit handoff intent and a later explicit confirmation of the rendered proposal; treat the initial handoff request as intent, not confirmation.
