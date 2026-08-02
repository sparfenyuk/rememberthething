## Context

See `proposal.md` for the motivation. The current repository stores flat `blueprints`, `journeys`, and `packs`; `include_pack` copies common items plus one complete variant into a target. The existing checklist items, provenance fields, explicit promotion flow, structured hints, and MCP App are useful seams to preserve.

## Goals / Non-Goals

**Goals:**

- Make reusable modules and trip composition first-class persisted state.
- Keep materialized journey items stable and editable after composition.
- Make variant deltas, nested modules, and one-of choices deterministic and inspectable by an LM.
- Preserve the existing concrete checklist mutation and rendered todo-list interaction.
- Provide a bounded migration path for existing SQLite databases.

**Non-Goals:**

- Conditional rules, computed quantities, tags/search, or persistent car/home inventory.
- Server-side recommendations or automatic variant selection.
- Live inheritance where editing a module silently changes an existing checklist.

## Decisions

### 1. Modules are definitions; blueprints and journeys are compositions

Add a module definition model with stable `item_key` values. A module owns common item definitions, variant deltas, nested module references, and choice groups. A blueprint and journey store selected module references and direct extras; their existing concrete `items` remain the materialized checklist representation.

This preserves the current snapshot UX while adding composition. A fully live graph would make user edits and removals surprising. A flat-only rewrite would retain the current duplication problem.

### 2. Use relational composition tables and explicit graph validation

Use `modules`, `module_items`, `module_variants`, `module_variant_adds`, `module_variant_removes`, `module_includes`, and `module_choices`/options tables. Use target composition tables for blueprint and journey module selections, including the selected variant and resolved choice options.

Validate include cycles transactionally before saving. Resolve nested modules depth-first with stable position ordering and a visited stack. A repeated source item becomes a reported composition conflict unless it is the same stable source key already materialized.

The implementation may keep small JSON fields for choice selections if that materially reduces schema complexity, but module definitions and include edges must remain queryable and validated rather than hidden in one untyped blob.

### 3. Variants operate on stable keys, not names

Common module items and variant additions use stable keys. Variant removals reference keys owned by the same module. Display names remain editable. This avoids breaking a variant when a user renames `car documents` and avoids unsafe fuzzy matching.

Existing full-list pack variants are migrated by deriving deterministic keys from names, treating items present only in the variant as `add`, and treating common keys absent from the old full list as `remove`. Collisions receive deterministic suffixes and are reported in migration diagnostics.

### 4. Materialization is explicit and idempotent

Introduce one shared resolver that expands selected modules, applies each module's selected variant, resolves selected choices, and returns concrete definitions plus provenance paths. `include_module` materializes a new selection; `refresh_composition` re-runs resolution for existing selections.

Materialized rows gain a stable composition/source key. Removing a module-sourced row records a target exclusion before deleting it; refresh skips excluded keys. Manual edits remain on the existing row. New duplicate definitions produce conflicts and never overwrite an edited row. Module and blueprint edits do not rewrite existing target rows unless refresh is explicitly requested.

This is smaller and safer than attempting a general merge engine. The known ceiling is that conflict resolution remains user/LM-driven; the server reports the alternatives but does not guess.

### 5. Keep the MCP surface explicit

Expose `list_modules`, `get_module`, `create_module`, `update_module`, and `delete_module`; replace `include_pack` with `include_module`; add `select_module_option` and `refresh_composition`. Keep existing journey, blueprint, and concrete item operations, changing only their composition fields and result payloads.

The old pack names are not the canonical contract. If migration compatibility is needed for an existing client, aliases may delegate to module operations during the transition, but they must not create a second behavior path or appear as the preferred hints.

### 6. Resolve choices explicitly in both LM and UI paths

An include or refresh operation returns unresolved choice records and a bounded next step for `select_module_option`. No variant or one-of option is inferred from season, destination, or names. The UI renders these records alongside the todo list and calls the same selection tool.

Conditions and formulas are intentionally deferred so the resolver remains a deterministic graph expansion rather than an expression runtime.

## Risks / Trade-offs

- [The schema change is breaking for current pack callers] → Make module tools canonical, document the migration, and keep compatibility aliases only if they delegate to the same implementation.
- [Old full-list variants lose intent during migration] → Derive add/remove deltas by stable normalized keys, preserve the original snapshot where possible, and expose migration conflicts.
- [Nested modules create duplicate items or cycles] → Validate cycles on write, resolve with a visited stack, preserve source paths, and return conflicts instead of overwriting.
- [Refresh could re-add something the user removed] → Persist composition exclusions keyed to the materialized source and skip them on every refresh.
- [The new UI becomes a module manager instead of a checklist] → Keep the todo list primary; show composition metadata and decisions as compact source/choice affordances.
- [A future rule engine may want different item identity] → Keep stable item keys and resolver boundaries now; do not add speculative condition syntax in this change.

## Migration Plan

1. On startup, detect the existing pack schema and create the module/composition tables.
2. Convert each pack to a module. Convert old common items to common module items. Convert each complete variant into add/remove deltas by normalized stable key.
3. Preserve existing blueprint, journey, and materialized item rows. Map old pack provenance to migrated module IDs where possible.
4. Make the migration transactional and idempotent; record non-fatal key collisions as structured diagnostics without blocking unrelated data.
5. Expose only the new module contract in fresh tool discovery. Keep any compatibility alias read/write path temporary and behaviorally delegated.
6. Rollback is source-version rollback. The migration must not delete old pack tables until the new representation has been verified; if a rollback path is needed, retain them as read-only migration input.
