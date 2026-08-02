## Why

People forget ordinary travel and activity essentials because remembering what to bring competes with planning the journey itself. This change creates a FastMCP application that lets an LM gather context conversationally while a rendered MCP App gives the user a fast, familiar todo-list surface.

## What Changes

- Add persistent journey checklists with reusable blueprints for future journeys.
- Let users create a journey from a blueprint, add or remove items during any phase, and mark items packed or unneeded.
- Preserve explicitly added ad-hoc items as candidates for the next blueprint; do not silently promote them.
- Add reusable packs such as bathroom essentials, hiking gear, or vacation basics.
- Support pack variants and context labels such as summer/winter so a vacation checklist can combine common items with the relevant seasonal clothing.
- Expose a small, non-overlapping MCP tool contract for list, item, blueprint, and pack operations.
- Return structured, context-aware `next_steps` hints from relevant tools so the LM can discover useful follow-on operations instead of guessing.
- Render the main checklist as an MCP App UI optimized for scanning, checking off, adding, editing, and removing items.
- Keep the server focused on storage, list operations, and deterministic follow-on affordances; the connected LM owns conversational gathering, photo understanding, and final recommendations.
- Ship the Python/uv FastMCP app with the LMStash import manifest, streamable HTTP MCP endpoint, health endpoint, and durable local storage declaration.

## Capabilities

### New Capabilities

- `journey-checklists`: Create and manage mutable journey checklists, reusable blueprints, journey context, item state, and explicit blueprint updates.
- `reusable-packs`: Store reusable item groups and seasonal/context variants that can be combined into a journey or blueprint.
- `mcp-list-ui`: Provide a rendered MCP App checklist surface and tool responses that keep the todo list as the primary interaction.

### Modified Capabilities

None. The new capabilities above include their structured next-step guidance requirements.

## Impact

- New Python FastMCP server, persistence layer, MCP tools, and rendered MCP App resource.
- New LMStash-compatible `.mcpcloud/app.yaml`, frozen `uv` project metadata, health route, and durable storage mount contract.
- New structured tool-result guidance contract and unit/integration coverage for list lifecycle, pack composition, hints, persistence, and UI-facing state.
- No image-processing service, recommendation engine, account-sharing model, or separate web application in this change.
