## Why

The first seasoned user found variants too brittle and simplified them away. The current snapshot-based pack model treats every variant as a complete item list, so composing a trip requires the LM to manage duplication, ordering, and explicit variant calls instead of assembling reusable building blocks.

This is the right time to pivot the domain toward composition before more modules and clients depend on the flat-pack contract.

## What Changes

- Introduce reusable `module` definitions as the canonical composition unit for everyday, work, car, toiletries, video, and activity groups.
- Make module variants deltas with explicit `add` and `remove` operations instead of complete replacement lists.
- Allow modules to include other modules, with cycle rejection and provenance preserved through the composition graph.
- Add `one_of` choice groups for mutually exclusive items such as camera lenses or training equipment.
- Let a journey or reusable trip blueprint store selected modules plus ad-hoc extras, then materialize a concrete todo checklist from that composition.
- Preserve user edits, removals, and item provenance when a composition is materialized or refreshed.
- Keep the todo-like MCP App and LM-driven tool workflow; expose unresolved choices and required inputs as structured results and next steps.
- **BREAKING**: make the compositional module contract canonical; the existing full-list pack variant shape and pack-only composition API become migration/compatibility concerns.
- Explicitly defer conditional rules, computed quantities, tags/search, and persistent inventories to later changes.

## Capabilities

### New Capabilities

- `composable-journeys`: Compose reusable modules and trip blueprints into stable, editable journey checklists with deltas, nested modules, and explicit choices.

### Modified Capabilities

None. The repository has no canonical `openspec/specs/` capability files yet; this change defines the next domain contract.

## Impact

- Replace the current `packs`/`pack_items` persistence shape with module definitions, module composition edges, delta variants, and choice groups.
- Extend blueprints and journeys with selected module references, composition context, materialization state, and durable user overrides.
- Change MCP tool inputs/results for module CRUD, composition, variant deltas, and unresolved choices while keeping concrete checklist mutations and the rendered UI.
- Update repository/service tests, MCP schemas, README, and deployment-independent SQLite initialization.
