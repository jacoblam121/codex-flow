# Execution model selection

The seven automatic choices and their concise mappings are canonical in [SKILL.md](../SKILL.md). Use Sol's bounded semantic judgment to recommend the lowest adequate supported choice. The launcher and current catalog mechanically validate the exact pair. Do not implement or invent a keyword classifier, numeric token threshold, or runtime benchmark.

## Selection mechanics

Select the lowest adequate supported choice described in [SKILL.md](../SKILL.md) and give one short rationale. Capability and correctness risk outrank horizon; use horizon to distinguish Luna max from Sol medium only after Tier 4 is judged adequate. If Tier 4 is unnecessary, remain on Luna xhigh. If its horizon is unclear, prefer Luna max.

Luna max and Sol medium are Tier-4 peers, not sequential rungs. Prefer Luna max for shorter, bounded work requiring concentrated reasoning and Sol medium for long-horizon, multi-stage work where token efficiency justifies its greater monetary cost. If one peer is unavailable, use the other when still adequate and disclose the tradeoff. A horizon-driven switch between them is rerouting, not capability escalation. Insufficient work from either upper-tier peer escalates to Sol high, then Sol max.

Sol high may be selected directly for inherently complex, architecture-sensitive, low-level/systems, concurrency, compiler/runtime, performance, memory-safety/security, cross-component invariant, correctness-critical, or otherwise technically unforgiving work. It is not reserved only for failed Tier 4 work. Sol max is for the highest-risk or highest-uncertainty work, novel cross-system/global synthesis, or insufficient Sol-high work.

If a choice is unavailable, use the next adequate supported choice and disclose why; do not jump directly to Sol merely because the source planner is Sol.

Never automatically recommend Luna high, Sol low/xhigh/ultra, Terra, or any other catalog entry. Any exact catalog-supported model/effort pair may be selected manually, including entries outside the frontier; manual selection never becomes an automatic choice. Recommendations may appear in the proposal; require explicit confirmation before dispatching, spawning, or applying a selection or escalation. Never change model or effort silently.
