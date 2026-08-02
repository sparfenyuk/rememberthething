"""Dependency-free smoke coverage for the core and MCP registration contract."""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.journey_checklist.repository import Repository
from src.journey_checklist.service import ChecklistService
from src.journey_checklist.ui import CHECKLIST_HTML, UI_URI


class FakeTool:
    def __init__(self, name: str, fn: object, app: object = None) -> None:
        self.name, self.fn, self.app = name, fn, app


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, FakeTool] = {}
        self.resources: dict[str, object] = {}

    def resource(self, uri: str, **_: object):
        def decorator(fn: object) -> object:
            self.resources[uri] = fn
            return fn

        return decorator

    def tool(self, **kwargs: object):
        def decorator(fn: object) -> object:
            self.tools[fn.__name__] = FakeTool(fn.__name__, fn, kwargs.get("app"))
            return fn

        return decorator


def install_fastmcp_stubs() -> None:
    fastmcp = types.ModuleType("fastmcp")
    fastmcp.FastMCP = FakeMCP
    apps = types.ModuleType("fastmcp.apps")
    apps.AppConfig = lambda **kwargs: kwargs
    tools = types.ModuleType("fastmcp.tools")
    tools.ToolResult = lambda **kwargs: kwargs
    mcp = types.ModuleType("mcp")
    mcp_types = types.ModuleType("mcp.types")
    mcp_types.TextContent = lambda **kwargs: kwargs
    sys.modules.update(
        {
            "fastmcp": fastmcp,
            "fastmcp.apps": apps,
            "fastmcp.tools": tools,
            "mcp": mcp,
            "mcp.types": mcp_types,
        }
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repository = Repository(Path(directory) / "journey.sqlite3")
        service = ChecklistService(repository)
        blueprint = repository.create_blueprint("work", [{"name": "passport"}])
        journey = service.start_journey("Berlin", {"season": "winter"}, blueprint["id"])
        journey_id = journey["affected"]["journey"]["id"]
        added = service.add_items("journey", journey_id, [{"name": "umbrella", "group": "weather"}])
        assert added["next_steps"][0]["tool"] == "promote_items"
        assert repository.get_journey(journey_id)["item_count"] == 2
        module = repository.create_module(
            "winter gear",
            [{"name": "gloves"}],
            [{"label": "winter", "add": [{"name": "coat"}], "remove": []}],
        )
        included = service.include_module("journey", journey_id, module["id"], "winter")
        assert included["affected"]["target"]["item_count"] == 4
        ad_hoc = service.add_items("journey", journey_id, [{"name": "adapter"}])
        ad_hoc_id = ad_hoc["affected"]["item_ids"][0]
        promoted = service.promote_items(journey_id, [ad_hoc_id], blueprint_id=blueprint["id"])
        assert promoted["affected"]["blueprint"]["item_count"] == 2
        removed = service.remove_items("journey", journey_id, [ad_hoc_id])
        assert ad_hoc_id not in {item["id"] for item in removed["affected"]["target"]["items"]}

    install_fastmcp_stubs()
    from src.journey_checklist.tools import register_tools

    fake = FakeMCP()
    register_tools(fake, ChecklistService(Repository(":memory:")))
    expected = {
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
    assert expected == set(fake.tools)
    assert UI_URI in fake.resources
    assert "next_steps" in CHECKLIST_HTML
    assert "tools/call" in CHECKLIST_HTML and "postMessage" in CHECKLIST_HTML


if __name__ == "__main__":
    main()
