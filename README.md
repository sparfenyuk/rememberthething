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

## LMStash contract

`.mcpcloud/app.yaml` is the authoritative LMStash manifest for the runtime, ASGI entrypoint, MCP transport, health route, OAuth, resources, and durable storage. Run the platform checker when the `lmstash` CLI is available:

```sh
lmstash check
```

For a hosted runtime, set `LMSTASH_ALLOWED_HOSTS` and `LMSTASH_ALLOWED_ORIGINS` to JSON string arrays and configure `LMSTASH_ORIGIN_TOKEN`; MCP requests then require `X-LMStash-Origin-Token`. Health remains unauthenticated.

## Tool and UI contract

The tools are target-explicit: journeys and blueprints own concrete materialized item rows plus selected module references and direct extras. Modules own stable item keys, nested includes, variant add/remove deltas, and explicit `one_of` choices. `include_module` and `refresh_composition` materialize snapshots; edits and durable removals survive refresh. Direct journey items are never promoted implicitly. `next_steps` contains bounded hints with tool names, safe arguments, missing inputs, and confirmation requirements; hints never trigger a mutation.

`start_journey` and `get_journey` advertise `ui://journey-checklist/checklist.html`. Compatible MCP Apps clients render the same persisted journey as a narrow-width-safe todo surface. Tool-only clients receive the same structured envelope:

```json
{
  "summary": "Items added.",
  "affected": {"target": "..."},
  "next_steps": []
}
```

Every tool advertises a generated output schema for this envelope. `affected` contains the operation-specific payload, including selected modules, source paths, unresolved choices, and conflicts; rejected operations include `error` without changing the text content or `isError` signal.

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
