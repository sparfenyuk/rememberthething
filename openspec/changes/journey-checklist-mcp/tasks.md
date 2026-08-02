## 1. Project and LMStash bootstrap

- [x] 1.1 Create the Python 3.12 `uv` project, pin compatible FastMCP/MCP Apps dependencies, and generate the frozen lockfile.
- [x] 1.2 Add `.mcpcloud/app.yaml` with the ASGI entrypoint, `/mcp` streamable HTTP contract, `/healthz`, OAuth scopes, resource limits, and one durable `/data` storage mount.
- [x] 1.3 Add the FastMCP/ASGI application shell, readiness route, allowed-host/origin-token middleware, and SQLite path validation for the LMStash runtime environment.
- [x] 1.4 Add a README covering local run, manifest preflight, LM-driven photo workflow, durable storage, and the tool/UI contract.

## 2. Persistence and domain model

- [x] 2.1 Implement SQLite schema and transactional repository operations for blueprints, journeys, items, packs, variants, and source provenance.
- [x] 2.2 Implement blueprint-to-journey snapshot creation and explicit journey-item promotion without implicit blueprint mutation.
- [x] 2.3 Implement journey context and item mutations, including add, edit, remove, packed/not-needed state, stable IDs, validation, and no-partial-write errors.
- [x] 2.4 Implement pack composition with common items, explicit variants, provenance, and duplicate/conflict reporting that preserves edited target items.
- [x] 2.5 Add focused repository tests covering independent snapshots, ad-hoc carry-forward, removals, seasonal variants, pack immutability, and restart persistence.

## 3. MCP tool contract

- [x] 3.1 Expose read tools for blueprints, journeys, and packs with compact summaries plus complete selected-target state.
- [x] 3.2 Expose single-purpose mutation tools for journey creation/update, item add/update/remove, item promotion, pack CRUD, and pack inclusion.
- [x] 3.3 Define the structured tool-result envelope with affected state, concise summary, and bounded `next_steps` hints.
- [x] 3.4 Implement deterministic hint rules for blueprint-to-journey, ad-hoc item, missing-context, pack, and explicit carry-forward transitions; never chain mutations.
- [x] 3.5 Ensure every mutation uses explicit target IDs, bounded inputs, and clear validation/conflict errors without generic action dispatch.
- [x] 3.6 Add MCP client tests for initialize, tools/list, representative blueprint/journey/pack flows, hint payloads, and tool-only fallback behavior.

## 4. MCP App checklist UI

- [x] 4.1 Confirm the pinned FastMCP/MCP Apps UI resource and tool-result metadata API, then isolate it behind one UI adapter.
- [x] 4.2 Implement the rendered journey view with context header, completion summary, grouped todo rows, packed/not-needed states, and remaining-work emphasis.
- [x] 4.3 Implement add, edit, check/uncheck, remove, blueprint, and pack actions through the shared MCP tools; keep UI state server-authoritative.
- [x] 4.4 Render `next_steps` as explicit UI actions, collect missing inputs, and require confirmation where indicated.
- [x] 4.5 Make the UI keyboard-accessible, narrow-width safe, and explicit about mutation errors and unsaved/rejected state.
- [ ] 4.6 Add a compatible-client render smoke test and verify that LM mutations, hint actions, and UI mutations converge on the same persisted state.

## 5. End-to-end verification and handoff

- [ ] 5.1 Verify `lmstash check`, frozen `uv` installation, `/healthz`, host/origin handling, and streamable HTTP MCP startup locally.
- [x] 5.2 Exercise the complete journey flow: blueprint → contextual journey → common/seasonal packs → ad-hoc item → explicit promotion → removal.
- [ ] 5.3 Run the repository gate: formatting/lint, type checks, focused tests, full tests, manifest validation, and MCP App smoke coverage.
- [x] 5.4 Review the final diff against all three capability specs and the LMStash deployment contract; leave implementation ready for the Herdr/5.6-luna execution pass.
