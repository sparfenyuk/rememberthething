# Journey Checklist MCP

Persistent journey checklists, reusable blueprints, and composable modules exposed as a small FastMCP server.

## Local run

Requires Python 3.12 and `uv`.

```sh
mkdir -p .data
JOURNEY_CHECKLIST_DB=.data/journey_checklist.sqlite3 uv run uvicorn src.server:app --reload
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`; readiness is `http://127.0.0.1:8000/healthz`.
The app defaults to `/data/journey_checklist.sqlite3` when `JOURNEY_CHECKLIST_DB` is not set, matching the declared LMStash mount.

## Use it with ChatGPT

Deploy the server first so ChatGPT can reach its `/mcp` endpoint. In the ChatGPT desktop app, open **Settings → MCP servers → Add server**, choose **Streamable HTTP**, enter the deployed MCP URL, save, and restart ChatGPT. Type `/mcp` in the composer to confirm that the server is connected. ChatGPT web uses remote MCP tools supplied by an enabled plugin in a ChatGPT Work workspace; it cannot reach a local `127.0.0.1` server.

The server stores journeys, blueprints, packs, and checklist state. ChatGPT handles the conversation: it can ask for missing trip details, interpret a packing photo, choose an explicit pack variant, and call the tools. Review write actions when ChatGPT asks for confirmation. The server returns `next_steps` after relevant actions so ChatGPT can suggest a pack, variant, or blueprint promotion without making that extra change silently.

### Travelling for a week

Start with a natural-language request:

```text
Start a journey called “Lisbon vacation”. I will stay 7 days in Lisbon in July.
Use my vacation blueprint, include the warm-weather variant of my Vacation pack,
and show me the checklist. Ask before adding anything that is not already in
the blueprint or pack.
```

Continue the same conversation as plans change:

```text
I attached a photo of the things on my bed. Identify the items you can see and
add only the items I confirm to the Lisbon journey. Afterward, tell me which
new items could be promoted to my vacation blueprint, but do not promote them
yet.
```

### Short business trip

```text
Create a journey called “Berlin client visit” for a 2-day business trip in
October. Start with my Work blueprint and include Toiletries. Ask me which
variant to use when a pack has alternatives. Then show the todo list.
```

The checklist can be updated during preparation:

```text
Mark the laptop and presentation clicker as packed, remove the second pair of
shoes, and add a USB-C charger. Keep the charger as a direct journey item for
now; suggest how I can add it to my Work blueprint for future trips.
```

### One-day weekend hike

```text
Start a journey called “Saturday hike” for a one-day hike in the Harz
Mountains this weekend. Use my Hiking pack, exclude overnight items, and ask
which alternatives to choose for any one-of-many items. Keep the checklist
focused on things I need to carry today.
```

If the same hike becomes a recurring activity:

```text
I added a headlamp and blister kit to this journey. Promote both to my Weekend
Hiking blueprint so they appear next time, then show the remaining unpacked
items.
```

The app does not receive photo bytes or make travel recommendations itself. ChatGPT interprets the conversation or attached image and sends the resulting item names and trip context to the MCP tools.

## LMStash contract

`.mcpcloud/app.yaml` is the authoritative LMStash manifest for the runtime, ASGI entrypoint, MCP transport, health route, OAuth, resources, and durable storage. Run the platform checker when the `lmstash` CLI is available:

```sh
lmstash check
```

For a hosted runtime, set `LMSTASH_ALLOWED_HOSTS` and `LMSTASH_ALLOWED_ORIGINS` to JSON string arrays and configure `LMSTASH_ORIGIN_TOKEN`; MCP requests then require `X-LMStash-Origin-Token`. Health remains unauthenticated.

## Tool and UI contract

The tools are target-explicit: journeys and blueprints own concrete materialized item rows plus selected module references and direct extras. Modules own stable item keys, nested includes, variant add/remove deltas, and explicit `one_of` choices. `include_module` and `refresh_composition` materialize snapshots; edits and durable removals survive refresh. Pass an existing selection's `selection_id` to `include_module` when applying a variant so the selection is updated instead of duplicated; initial selections with variants expose that same update hint. Module updates require explicit `item_key` values when replacing common or variant-added items, and explicit `option_key` values when replacing choice options. Direct journey items are never promoted implicitly. `next_steps` contains bounded hints with tool names, safe arguments, missing inputs, and confirmation requirements; the current selection takes priority over older suggestions. Hints never trigger a mutation.

`start_journey` and `get_journey` advertise `ui://journey-checklist/checklist.html`. Compatible MCP Apps clients render the same persisted journey as a narrow-width-safe todo surface. Tool-only clients receive the same structured envelope:

```json
{
  "summary": "Items added.",
  "affected": {"target": "..."},
  "next_steps": []
}
```

Every tool advertises a generated output schema for this envelope. `affected` contains the operation-specific payload, including selected modules, source paths, unresolved choices, and conflicts; rejected operations include `error` in the text content and set the MCP `isError` signal.

For exact MCP arguments, clients should use each tool's generated `inputSchema`. Composable inputs are typed for module items, includes, variants, choices, selections, and journey context; each choice needs at least one option, and object inputs reject unknown fields.

Existing SQLite pack tables remain as read-only migration input. Startup converts each pack to a module with deterministic stable keys and variant deltas, preserving existing checklist rows and provenance where possible. Name conflicts receive deterministic suffixed module names and one migration diagnostic. Migration is idempotent. New clients should use the module tools; conditions, computed quantities, tags/search, and persistent inventory are intentionally deferred.

## LM-driven photo workflow

The connected LM owns the conversation: gather destination, dates, duration, purpose, and season; understand any user-provided packing photo; choose modules, variants, and explicit choice options; then call the tools. The server stores checklist context, item data, reusable blueprints and modules, and item provenance. It does not accept photo bytes, call vision services, infer recommendations, or silently choose variants or one-of options.

## Verification

```sh
UV_PYTHON=3.12 uv sync --frozen --all-groups
UV_PYTHON=3.12 uv run ruff format --check .
UV_PYTHON=3.12 uv run ruff check .
UV_PYTHON=3.12 uv run mypy src
UV_PYTHON=3.12 uv run pytest
```
