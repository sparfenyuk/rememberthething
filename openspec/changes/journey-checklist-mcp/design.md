## Context

The repository currently contains only OpenSpec configuration. The app must fit the existing LMStash portable app contract: Python 3.12, frozen `uv` builds, an ASGI entrypoint, streamable HTTP MCP at `/mcp`, unauthenticated readiness at `/healthz`, and one declared durable storage mount. See the proposal and capability specs for the user-facing contract.

## Goals / Non-Goals

**Goals:**

- Keep one authoritative persisted checklist state shared by MCP tools and the rendered MCP App.
- Make blueprints, journeys, packs, and variants distinct concepts with explicit operations.
- Preserve provenance so direct additions can be carried forward deliberately.
- Give the LM concrete next actions through structured tool-result hints instead of relying on guessed tool sequences.
- Keep the LM responsible for conversational planning and image understanding.
- Provide an implementation path that is easy to exercise locally and through LMStash.

**Non-Goals:**

- Server-side vision, image uploads, photo storage, or an AI recommendation engine.
- A separate web application, calendar integration, travel-data lookup, or weather lookup.
- Multi-user sharing, teams, household permissions, or an account model inside the app.
- Automatic promotion of items, automatic seasonal recommendations, or silent overwrite of edited items.

## Decisions

### Snapshot-based domain model

Use four persisted concepts:

- `blueprint`: a named reusable checklist definition.
- `journey`: an independent checklist created ad hoc or from a blueprint, with optional context fields.
- `pack`: a reusable named group with common items and zero or more labeled variants.
- `item`: a concrete row owned by a blueprint or journey, with name, optional group, quantity, unit, note, packed/not-needed state, and source provenance.

Starting a journey copies blueprint items. Including a pack also copies its selected items. Copies retain source metadata for UI display and explicit promotion, but later pack or blueprint edits do not rewrite existing targets. This snapshot model keeps an in-progress trip stable while the user maintains reusable material separately.

### Small target-explicit MCP surface

Use clear nouns and single-purpose mutations. Avoid a generic `manage` tool with an action enum.

| Tool | Responsibility |
| --- | --- |
| `list_blueprints` / `get_blueprint` | Read reusable blueprints and their items. |
| `create_blueprint` | Create an empty or supplied blueprint. |
| `start_journey` / `get_journey` | Create or read an independent journey, including context. |
| `update_journey` | Change journey name/context only. |
| `add_items` | Add one or more concrete items to one journey or blueprint target. |
| `update_items` | Change existing item fields or packed/not-needed state. |
| `remove_items` | Remove selected items from one target. |
| `promote_items` | Explicitly copy selected direct journey items into a blueprint. |
| `list_packs` / `get_pack` | Read packs, common items, and variant metadata. |
| `create_pack` / `update_pack` / `delete_pack` | Maintain reusable packs and variants. |
| `include_pack` | Copy a chosen pack and optional variant into one journey or blueprint. |

Every mutation requires the target identifier where applicable, returns the affected state plus a concise result summary, and reports validation conflicts without partial writes. Relevant results also include a `next_steps` array; an empty array is valid. `include_pack` requires an explicit variant when the caller wants one; the server exposes metadata but does not infer recommendations. Tool schemas use stable IDs and bounded lists so an LM can call them safely in a conversation.

### Structured next-step hints

Hints are deterministic affordances attached to the result that created the opportunity. They do not form a second recommendation engine and never trigger another mutation. A hint has this shape:

```json
{
  "tool": "promote_items",
  "reason": "These direct items can be remembered in the blueprint.",
  "arguments": {"journey_id": "...", "item_ids": ["..."]},
  "needs": [],
  "requires_confirmation": true
}
```

The server emits hints from explicit state transitions:

- `start_journey` can point to `list_packs` and `include_pack` when the blueprint can be extended and context such as season or activity is missing.
- `add_items` can point to `promote_items` and, for grouped direct items, `create_pack` or `update_pack`.
- `update_journey` can point to the same journey update when missing context blocks a deliberate pack variant choice.
- Pack and blueprint reads can expose only follow-on operations supported by the returned IDs and current state.

Hints carry known IDs and safe arguments, list missing inputs instead of guessing them, and mark destructive or persistent follow-ons as confirmation-required. Cap each result at a small number of high-value hints so routine checkbox updates do not become noisy. Do not persist hints; regenerate them from the current state so stale actions cannot become authoritative. A tool-only client can ignore the field while an LM can use it as a compact action map.

The alternatives are a dedicated `suggest_next_steps` tool or free-form prose appended to every response. The dedicated tool adds another call that an LM may omit; prose loses stable tool names, IDs, and confirmation semantics. Embedding bounded structured hints in existing results keeps discovery adjacent to the state change and preserves the small tool surface.

### MCP App as a thin stateful view

Expose one checklist UI resource for the selected journey using the MCP Apps integration supported by the pinned FastMCP/MCP Apps dependencies. The resource renders grouped items and calls the same MCP tools for mutations; it does not maintain a second database or invent client-only state. The UI includes a compact journey header, completion summary, grouped todo rows, add/edit/remove controls, and pack/blueprint actions. It must work at narrow widths and with keyboard/focus navigation.

The implementation task must first confirm the exact UI resource and tool-result metadata API supported by the pinned dependency set, then lock that API behind the app's single UI adapter. This keeps the product contract stable if the FastMCP integration surface differs from the protocol terminology.

### SQLite on the LMStash durable mount

Use one SQLite database under `/data`, with transactions around each mutation. Declare one LMStash storage entry with a stable name, absolute mount path `/data`, and an implementation-selected positive size. Do not use an external database for the first version. The app manifest remains portable and contains no provider-specific fields.

### LM-driven composition

The server stores context, exposes packs/variants, and returns deterministic next-step hints. The LM gathers destination, duration, purpose, dates, and season; interprets user-provided photos; chooses relevant packs or variants; decides whether to follow hints; and calls the mutation tools. Photo bytes never enter the app. This keeps the server deterministic and avoids overlapping a recommendation engine with the model already driving the conversation.

### Deployment and verification

Package the app as `src.server:app`, with FastMCP mounted at `/mcp` using streamable HTTP and a 2xx `/healthz` route. Add the `.mcpcloud/app.yaml` declaration for Python/uv, OAuth scopes, resource limits, and durable storage. Local verification uses the repository's `uv` workflow, the LMStash manifest preflight, a real MCP initialize/tools-list exchange, persistence across process restart, and an MCP App render smoke test where a compatible client is available.

## Risks / Trade-offs

- [UI integration API differs across FastMCP releases] → Pin a known compatible version, isolate the UI adapter, and run a client render smoke test before implementation is considered complete.
- [SQLite file is lost without a correctly declared mount] → Make the storage declaration and startup path part of the same acceptance gate; fail clearly if `/data` is unavailable or not writable.
- [Pack composition creates confusing duplicates] → Preserve the existing edited row, return explicit conflict details, and require the LM/user to choose; never silently overwrite.
- [Snapshot copies become stale] → Keep provenance visible and provide explicit blueprint/pack update operations rather than hidden live inheritance.
- [Large lists overwhelm an LM] → Return compact summaries for list operations, full state for a selected target, and bounded bulk mutations.
- [Hints become repetitive or noisy] → Emit only state-triggered, high-value hints, cap the count, and return an empty array for routine operations.
