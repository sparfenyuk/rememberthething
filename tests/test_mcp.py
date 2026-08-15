from __future__ import annotations

import asyncio
import json
import os
import subprocess
from html.parser import HTMLParser
from importlib import import_module

import httpx
import pytest
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

TOOL_NAMES = {
    "list_blueprints",
    "get_blueprint",
    "create_blueprint",
    "start_journey",
    "get_journey",
    "update_journey",
    "add_items",
    "update_items",
    "remove_items",
    "promote_items",
    "list_modules",
    "get_module",
    "create_module",
    "update_module",
    "delete_module",
    "include_module",
    "select_module_option",
    "refresh_composition",
}


class UIContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.input_ids: set[str] = set()
        self.labels: dict[str, str] = {}
        self.scripts: list[str] = []
        self._label_for: str | None = None
        self._label_text: list[str] = []
        self._script: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("id"):
            self.input_ids.add(attributes["id"])
        elif tag == "label":
            self._label_for = attributes.get("for")
            self._label_text = []
        elif tag == "script":
            self._script = []

    def handle_data(self, data: str) -> None:
        if self._label_for is not None:
            self._label_text.append(data)
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "label" and self._label_for is not None:
            self.labels[self._label_for] = "".join(self._label_text).strip()
            self._label_for = None
        elif tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script))
            self._script = None


def execute_ui_script(script: str) -> list[dict[str, object]]:
    harness = r"""
const fs = require('node:fs');
const source = fs.readFileSync(0, 'utf8');
const posted = [];
let receiveMessage;
const elements = new Map();
global.window = {
  addEventListener(type, handler) { if (type === 'message') receiveMessage = handler; },
  parent: {
    postMessage(message) {
      posted.push(message);
      if (message.method === 'ui/initialize') {
        queueMicrotask(() => receiveMessage({data: {id: message.id, result: {}}}));
      }
    },
  },
};
global.document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, {addEventListener() {}});
    return elements.get(id);
  },
};
eval(source);
setImmediate(() => process.stdout.write(JSON.stringify(posted)));
"""
    completed = subprocess.run(
        ["node", "-e", harness], input=script, text=True, capture_output=True, check=True
    )
    return json.loads(completed.stdout)


@pytest.mark.asyncio
async def test_mcp_initialize_tools_and_tool_only_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "mcp.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "mcp.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "Journey Checklist"
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    assert {"start_journey", "add_items", "include_module", "get_journey"} <= names
                    created = await session.call_tool("start_journey", {"name": "Berlin"})
                    payload = json.loads(created.content[0].text)
                    assert payload["affected"]["journey"]["name"] == "Berlin"


@pytest.mark.asyncio
async def test_all_tools_advertise_valid_output_schemas_and_keep_ui_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "tool-schemas.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "tool-schemas.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    assert {tool.name for tool in tools} == TOOL_NAMES
                    for tool in tools:
                        assert tool.outputSchema is not None
                        Draft202012Validator.check_schema(tool.outputSchema)

                    ui_tools = {
                        tool.name: tool
                        for tool in tools
                        if tool.name in {"start_journey", "get_journey"}
                    }
                    assert set(ui_tools) == {"start_journey", "get_journey"}
                    assert all(tool.meta is not None for tool in ui_tools.values())
                    assert {tool.meta["ui"]["resourceUri"] for tool in ui_tools.values()} == {
                        "ui://journey-checklist/checklist.html"
                    }


@pytest.mark.asyncio
async def test_composable_tools_advertise_typed_nested_input_schemas(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "input-schemas.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "input-schemas.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    schemas = {
                        tool.name: tool.inputSchema for tool in (await session.list_tools()).tools
                    }

                    def array_items(schema: dict[str, object], field: str) -> dict[str, object]:
                        variants = schema["properties"][field]["anyOf"]
                        return next(
                            item["items"] for item in variants if item.get("type") == "array"
                        )

                    module_schema = schemas["create_module"]
                    common_item = array_items(module_schema, "common_items")
                    assert {"item_key", "name", "group", "quantity", "unit", "note"} <= set(
                        common_item["properties"]
                    )
                    choice = array_items(module_schema, "choices")
                    assert {"choice_key", "label", "required", "options"} <= set(
                        choice["properties"]
                    )
                    option = choice["properties"]["options"]["items"]
                    assert {"option_key", "name", "group", "quantity", "unit", "note"} <= set(
                        option["properties"]
                    )
                    assert "options" in choice["required"]
                    assert choice["properties"]["options"]["minItems"] == 1
                    assert choice["properties"]["options"]["maxItems"] == 50
                    variant = array_items(module_schema, "variants")
                    assert {"add", "remove"} <= set(variant["properties"])
                    assert "item_key" in variant["properties"]["add"]["items"]["properties"]

                    update_schema = schemas["update_module"]
                    update_item = array_items(update_schema, "common_items")
                    assert "item_key" in update_item["required"]
                    update_choice = array_items(update_schema, "choices")
                    update_option = update_choice["properties"]["options"]["items"]
                    assert "option_key" in update_option["required"]

                    blueprint_item = array_items(schemas["create_blueprint"], "items")
                    assert {
                        "name",
                        "group",
                        "quantity",
                        "unit",
                        "note",
                        "packed",
                        "not_needed",
                    } <= set(blueprint_item["properties"])
                    assert "item_key" not in blueprint_item["properties"]
                    context = schemas["start_journey"]["properties"]["context"]["anyOf"][0]
                    assert {
                        "destination",
                        "purpose",
                        "start_date",
                        "end_date",
                        "duration_days",
                        "season",
                    } <= set(context["properties"])

                    include_choices = schemas["include_module"]["properties"]["choices"]["anyOf"]
                    choice_selection = next(
                        item["items"] for item in include_choices if item.get("type") == "array"
                    )
                    assert {"choice_key", "option_key", "module_id"} <= set(
                        choice_selection["properties"]
                    )
                    assert all(
                        schema.get("additionalProperties") is False
                        for schema in (common_item, choice, option, variant, choice_selection)
                    )


@pytest.mark.asyncio
async def test_success_and_error_envelopes_validate_across_tool_families(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "result-schemas.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "result-schemas.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = {tool.name: tool for tool in (await session.list_tools()).tools}

                    async def call_and_validate(
                        name: str, arguments: dict[str, object], *, is_error: bool = False
                    ) -> dict[str, object]:
                        result = await session.call_tool(name, arguments)
                        assert result.isError is is_error
                        assert result.structuredContent is not None
                        schema = tools[name].outputSchema
                        assert schema is not None
                        Draft202012Validator(schema).validate(result.structuredContent)
                        assert json.loads(result.content[0].text) == result.structuredContent
                        return result.structuredContent

                    await call_and_validate(
                        "create_blueprint",
                        {"name": "carry-on", "items": [{"name": "passport", "group": "documents"}]},
                    )
                    journey = await call_and_validate("start_journey", {"name": "Berlin"})
                    journey_id = journey["affected"]["journey"]["id"]
                    await call_and_validate(
                        "add_items",
                        {
                            "target_type": "journey",
                            "target_id": journey_id,
                            "items": [{"name": "passport", "group": "documents"}],
                        },
                    )
                    module = await call_and_validate(
                        "create_module",
                        {
                            "name": "essentials",
                            "common_items": [{"name": "passport", "group": "documents"}],
                            "variants": [
                                {"label": "summer", "add": [{"name": "hat"}], "remove": []}
                            ],
                        },
                    )
                    included = await call_and_validate(
                        "include_module",
                        {
                            "target_type": "journey",
                            "target_id": journey_id,
                            "module_id": module["affected"]["module"]["id"],
                        },
                    )
                    assert included["conflicts"]

                    await call_and_validate(
                        "get_blueprint", {"blueprint_id": "missing-blueprint"}, is_error=True
                    )
                    await call_and_validate(
                        "get_journey", {"journey_id": "missing-journey"}, is_error=True
                    )
                    await call_and_validate(
                        "include_module",
                        {
                            "target_type": "journey",
                            "target_id": journey_id,
                            "module_id": module["affected"]["module"]["id"],
                            "variant": "winter",
                        },
                        is_error=True,
                    )


@pytest.mark.asyncio
async def test_mcp_choice_follow_up_is_structured_and_tool_only(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "choice-flow.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "choice-flow.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    module_result = await session.call_tool(
                        "create_module",
                        {
                            "name": "Video",
                            "choices": [
                                {
                                    "choice_key": "lens",
                                    "label": "Lens",
                                    "options": [
                                        {"option_key": "prime", "name": "35mm"},
                                        {"option_key": "zoom", "name": "24-70"},
                                    ],
                                }
                            ],
                        },
                    )
                    module = json.loads(module_result.content[0].text)["affected"]["module"]
                    journey = json.loads(
                        (await session.call_tool("start_journey", {"name": "Trip"})).content[0].text
                    )["affected"]["journey"]
                    included = json.loads(
                        (
                            await session.call_tool(
                                "include_module",
                                {
                                    "target_type": "journey",
                                    "target_id": journey["id"],
                                    "module_id": module["id"],
                                },
                            )
                        )
                        .content[0]
                        .text
                    )
                    assert included["affected"]["unresolved_choices"]
                    assert included["next_steps"][0]["tool"] == "select_module_option"
                    selected = json.loads(
                        (
                            await session.call_tool(
                                "select_module_option",
                                {
                                    "target_type": "journey",
                                    "target_id": journey["id"],
                                    "selection_id": included["affected"]["selection_id"],
                                    "choice_id": "lens",
                                    "option_key": "prime",
                                },
                            )
                        )
                        .content[0]
                        .text
                    )
                    assert selected["affected"]["target"]["items"][0]["name"] == "35mm"


@pytest.mark.asyncio
async def test_mcp_nested_choice_selection_accepts_typed_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "nested-choice-inputs.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "nested-choice-inputs.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    child = json.loads(
                        (
                            await session.call_tool(
                                "create_module",
                                {
                                    "name": "Video",
                                    "choices": [
                                        {
                                            "choice_key": "lens",
                                            "label": "Lens",
                                            "options": [{"option_key": "prime", "name": "35mm"}],
                                        }
                                    ],
                                },
                            )
                        )
                        .content[0]
                        .text
                    )["affected"]["module"]
                    parent = json.loads(
                        (
                            await session.call_tool(
                                "create_module",
                                {
                                    "name": "Camera kit",
                                    "includes": [{"module_id": child["id"]}],
                                },
                            )
                        )
                        .content[0]
                        .text
                    )["affected"]["module"]
                    journey = json.loads(
                        (
                            await session.call_tool(
                                "start_journey",
                                {
                                    "name": "Trip",
                                    "context": {"destination": "Berlin", "duration_days": 3},
                                    "module_selections": [
                                        {
                                            "module_id": parent["id"],
                                            "choices": [
                                                {
                                                    "module_id": child["id"],
                                                    "choice_key": "lens",
                                                    "option_key": "prime",
                                                }
                                            ],
                                        }
                                    ],
                                },
                            )
                        )
                        .content[0]
                        .text
                    )["affected"]["journey"]

                    assert [item["name"] for item in journey["items"]] == ["35mm"]
                    assert journey["unresolved_choices"] == []


@pytest.mark.asyncio
async def test_origin_token_auth_statuses_and_healthz(tmp_path, monkeypatch):
    monkeypatch.setenv("LMSTASH_ORIGIN_TOKEN", "secret")
    monkeypatch.delenv("MCP_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "auth.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for headers, expected_status in (
                ({}, 401),
                ({"X-LMStash-Origin-Token": "wrong"}, 401),
                ({"X-LMStash-Origin-Token": "secret"}, 405),
            ):
                response = await client.get("/mcp", headers=headers)
                assert response.status_code == expected_status

            response = await client.get("/healthz")
            assert response.status_code == 200


def test_ui_contract_is_registered():
    os.environ.setdefault("JOURNEY_CHECKLIST_DB", "/tmp/journey-checklist-test.sqlite3")
    create_app = import_module("src.server").create_app
    UI_URI = import_module("src.journey_checklist.ui").UI_URI

    app = create_app("/tmp/journey-checklist-test.sqlite3")
    resource = asyncio.run(app.state.mcp.get_resource(UI_URI))
    assert resource is not None
    result = asyncio.run(app.state.mcp.read_resource(UI_URI))
    assert result.contents[0].meta == {
        "ui": {
            "csp": {
                "connectDomains": [],
                "resourceDomains": [],
                "frameDomains": [],
                "baseUriDomains": [],
            }
        }
    }
    parser = UIContractParser()
    parser.feed(result.contents[0].content)
    assert parser.labels["new-item"] == "Item name"
    assert "new-item" in parser.input_ids
    assert execute_ui_script(parser.scripts[0]) == [
        {
            "jsonrpc": "2.0",
            "id": "journey-1",
            "method": "ui/initialize",
            "params": {
                "protocolVersion": "2026-01-26",
                "appInfo": {"name": "journey-checklist", "version": "0.1.0"},
                "appCapabilities": {"availableDisplayModes": ["inline"]},
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "ui/notifications/initialized",
            "params": {},
        },
    ]


def test_ui_contract_uses_mcp_app_lifecycle_and_tool_notifications():
    ui = import_module("src.journey_checklist.ui")
    assert "sendRequest('ui/initialize'" in ui.CHECKLIST_HTML
    assert "ui/notifications/initialized" in ui.CHECKLIST_HTML
    assert "ui/notifications/tool-result" in ui.CHECKLIST_HTML
    assert "message?.params" in ui.CHECKLIST_HTML
    assert "value.method === 'tools/call'" not in ui.CHECKLIST_HTML
    assert "include_module" in ui.CHECKLIST_HTML
    assert "select_module_option" in ui.CHECKLIST_HTML
    assert "refresh_composition" in ui.CHECKLIST_HTML
    assert "source.path" in ui.CHECKLIST_HTML
    assert "Modules in this checklist" in ui.CHECKLIST_HTML
    assert 'data-choice="${escapeHtml(choice.choice_id)}"' in ui.CHECKLIST_HTML
    assert 'data-choice="${escapeHtml(choice.choice_key)}"' not in ui.CHECKLIST_HTML
