from __future__ import annotations

import asyncio
import json
import os
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
    "list_packs",
    "get_pack",
    "create_pack",
    "update_pack",
    "delete_pack",
    "include_pack",
}


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
                    assert {"start_journey", "add_items", "include_pack", "get_journey"} <= names
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
                    pack = await call_and_validate(
                        "create_pack",
                        {
                            "name": "essentials",
                            "common_items": [{"name": "passport", "group": "documents"}],
                            "variants": [{"label": "summer", "items": [{"name": "hat"}]}],
                        },
                    )
                    included = await call_and_validate(
                        "include_pack",
                        {
                            "target_type": "journey",
                            "target_id": journey_id,
                            "pack_id": pack["affected"]["pack"]["id"],
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
                        "include_pack",
                        {
                            "target_type": "journey",
                            "target_id": journey_id,
                            "pack_id": pack["affected"]["pack"]["id"],
                            "variant": "winter",
                        },
                        is_error=True,
                    )


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


def test_ui_contract_uses_mcp_app_lifecycle_and_tool_notifications():
    ui = import_module("src.journey_checklist.ui")
    assert "sendRequest('ui/initialize'" in ui.CHECKLIST_HTML
    assert "ui/notifications/initialized" in ui.CHECKLIST_HTML
    assert "ui/notifications/tool-result" in ui.CHECKLIST_HTML
    assert "message?.params" in ui.CHECKLIST_HTML
    assert "value.method === 'tools/call'" not in ui.CHECKLIST_HTML
