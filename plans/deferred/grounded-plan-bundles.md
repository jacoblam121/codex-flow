# Deferred Capability: Grounded and Phased Plan Bundles

## Status

Deferred until the core handoff, review, repair, routing, and installation phases are complete and accepted. This document preserves the product
decision without adding it to the first implementation.

## Motivation

Long planning threads are expensive to carry into execution, difficult to resume after time away, and often too broad for one implementation
agent. Codex Flow should eventually let users persist an approved plan as a durable Markdown artifact, split it into independently executable
phases, and return to it without depending on a live source session.

This capability must remain optional. Small tasks should continue to use the direct thread-to-executor handoff.

## Product Boundary

Codex Flow will coordinate grounded execution plans; it will not become a general project-management system.

Include:

- Adopt the latest approved `<proposed_plan>` or an existing Markdown file.
- Create a named plan bundle with a canonical master and bounded phase files.
- Validate phase structure, dependencies, hashes, and cycles deterministically.
- Hand off and review one phase at a time.
- Resume work from the bundle after the original planning session is closed.
- Keep execution and review history in the existing external run ledger.

Exclude from the initial grounded-plan release:

- Calendars, estimates, assignees, dashboards, or cloud synchronization.
- Automatic scheduling or unattended execution of dependency graphs.
- Automatic rewriting of tracked plan files after every run.
- Inferring plan acceptance from Git commits or file changes.
- Silently reconciling conflicting thread and file instructions.

## User Workflow

- `$codex-flow ground`
  - Offer the latest approved plan from the current exact thread.
  - Accept an explicit Markdown path as an alternative source.
  - Ask for a plan slug and destination before writing repository files.
  - Create a bundle only after confirmation.

- `$codex-flow split <plan>`
  - Have Sol choose milestone boundaries based on independently verifiable outcomes rather than arbitrary size.
  - Show the proposed phase manifest before writing it.
  - Create phase files only after approval.

- `$codex-flow validate <plan>`
  - Verify schema versions, IDs, referenced files, content hashes, dependency targets, acyclicity, and required Markdown sections.
  - Report drift without modifying files.

- `$codex-flow handoff <plan> --phase <id>`
  - Require all declared prerequisites to be accepted or explicitly overridden.
  - Embed the pinned phase content and relevant master constraints in the run bundle.
  - Record the plan ID, master hash, phase ID, and phase hash in the external run manifest.

- `$codex-flow review <plan> --phase <id>`
  - Retrieve the phase's latest execution report.
  - Audit against the phase acceptance criteria and applicable master constraints.
  - Record acceptance, rejection, or blockage in the external run ledger.

## Default Bundle Layout

```text
plans/<slug>/
├── master.md
├── manifest.json
└── phases/
    ├── 01-<phase-slug>.md
    ├── 02-<phase-slug>.md
    └── ...
```

Support explicitly supplied bundle roots, but generate this named layout by default so a repository can contain several plans.

## Authority and Revision Semantics

- Once grounded, the hashed `master.md` and phase files are authoritative for execution. The source conversation remains useful context but
  cannot silently override the files.
- `manifest.json` identifies the exact hashes that were approved. A mismatch is plan drift and blocks launch until the user approves a revision.
- Operational states such as launched, awaiting review, accepted, blocked, and superseded live in `~/.local/state/codex-flow`, keyed by plan
  ID and content hash. Routine execution must not dirty the repository's plan files.
- Revising a grounded plan is explicit. Revisions update the manifest and revalidate pending phases; accepted historical runs retain their
  original hashes.
- Never choose whichever source is newest. Conflicts require the user to select or approve the new authority.

## Manifest Contract

Use a versioned JSON manifest so deterministic tooling can read and write it without a YAML dependency. At minimum record:

- `schema_version`
- `plan_id`
- `title`
- `master_path` and `master_sha256`
- ordered phases with `phase_id`, `path`, `sha256`, and `depends_on`
- creation and revision timestamps
- optional originating thread ID and repository identity

Do not store operational phase status in the tracked manifest.

## Phase File Contract

Every phase file must contain:

- Outcome: one observable result.
- Prerequisites: accepted phases and required external state.
- Inputs and authoritative references.
- In-scope implementation work.
- Explicit exclusions.
- Public interfaces or state changes introduced by the phase.
- Validation scenarios and commands.
- Exit criteria that Sol can audit without making new product decisions.
- Required execution report fields.

A phase should fit one execution-and-review loop. If it cannot, split it before launch rather than delegating its decomposition to the executor.

## Decomposition Rules

- Prefer vertical milestones that leave a runnable or testable increment.
- Separate work when it has distinct failure modes, permissions, or review criteria.
- Keep tightly coupled schema and consumer changes together.
- Make dependencies explicit and acyclic.
- Avoid duplicating the whole master in every phase; include only phase-local instructions and reference the pinned master hash.
- Do not create phases whose only outcome is vague research. A research phase must produce a named decision artifact with acceptance criteria.
- Let Sol propose boundaries; use deterministic code only to validate the resulting structure.

## Failure Modes

- Missing or modified master/phase: block launch and show the hash mismatch.
- Dependency not accepted: block by default and offer an explicit override with rationale.
- Source thread unavailable: proceed from the validated bundle without requiring session recovery.
- Bundle manifest malformed or cyclic: refuse execution and report exact fields or edges to repair.
- Phase is too broad during handoff: return to planning and split it; do not let Luna silently reinterpret scope.
- Plan changes while a run is active: preserve the run's pinned snapshot and require a new revision for subsequent runs.

## Future Acceptance Criteria

- A user can ground a live approved plan and later launch a phase after closing the original Sol session.
- Multiple named plan bundles coexist in one repository without ambiguous selection.
- Editing a grounded phase is detected before launch.
- A dependency cycle or missing dependency is rejected with a precise diagnostic.
- Reviewing a phase updates only the external ledger and leaves tracked plan files unchanged.
- A phase handoff contains enough pinned context for a clean Luna session to execute without reading the original conversation.
