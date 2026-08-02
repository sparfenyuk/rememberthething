## 1. Domain and storage foundation

- [x] 1.1 Define module, stable item-key, variant-delta, nested-include, and one-of choice contracts without adding deferred conditions, formulas, tags, or inventory fields.
- [x] 1.2 Add transactional SQLite tables and indexes for modules, module items, variants, variant adds/removes, nested includes, choices, target module selections, and composition exclusions.
- [x] 1.3 Add an idempotent migration from existing packs and full-list variants to modules and add/remove deltas, preserving existing blueprint, journey, item, and provenance data.

## 2. Composition engine

- [x] 2.1 Implement module CRUD with stable item-key validation, include-edge validation, and direct/indirect cycle rejection.
- [x] 2.2 Implement deterministic nested-module resolution with variant deltas, explicit choice selections, source paths, stable composition keys, and duplicate conflict reporting.
- [x] 2.3 Implement target module selections and explicit `include_module`/`refresh_composition` materialization for journeys and blueprints.
- [x] 2.4 Preserve edited rows and durable removals during refresh; implement explicit one-of option selection and unresolved-choice results.

## 3. MCP contract and hints

- [x] 3.1 Replace canonical pack tools with non-overlapping module CRUD/read tools and update tool inputs/results to expose deltas, includes, choices, provenance, conflicts, and stable IDs.
- [x] 3.2 Add `include_module`, `select_module_option`, and `refresh_composition` while preserving existing concrete checklist mutations and explicit item promotion.
- [x] 3.3 Update bounded structured next-step hints and generated output schemas so an LM can discover variants, unresolved choices, conflicts, and refresh actions without guessing.

## 4. MCP App and documentation

- [x] 4.1 Keep the todo list primary while adding compact module/source-path display, unresolved choice actions, conflict feedback, and explicit refresh through shared MCP tools.
- [x] 4.2 Update README and OpenSpec-facing documentation for the module composition contract, migration behavior, and deferred capabilities.

## 5. Verification

- [x] 5.1 Add repository tests for stable keys, delta variants, nested composition/cycles, migration, one-of choices, refresh preservation, and conflicts.
- [x] 5.2 Add MCP tests for module discovery, tool-only composition flows, unresolved-choice follow-ups, output-schema validation, and UI metadata/state convergence.
- [x] 5.3 Run focused/full pytest, Ruff format/check, mypy, OpenSpec validation, and diff checks; review the final diff against the proposal and capability spec.
