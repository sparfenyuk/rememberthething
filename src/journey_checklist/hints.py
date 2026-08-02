from __future__ import annotations

from typing import Any


def _hint(
    tool: str,
    reason: str,
    arguments: dict[str, Any],
    *,
    needs: list[str] | None = None,
    confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "tool": tool,
        "reason": reason,
        "arguments": arguments,
        "needs": needs or [],
        "requires_confirmation": confirmation,
    }


def journey_hints(journey: dict[str, Any], modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if any(item["source"]["kind"] == "module" for item in journey["items"]):
        return []
    if not modules:
        return []
    has_variants = any(module["variants"] for module in modules)
    if has_variants and not journey["context"].get("season"):
        return [
            _hint(
                "update_journey",
                "Add the journey season before choosing a seasonal pack variant.",
                {"journey_id": journey["id"]},
                needs=["season"],
            )
        ]
    return [
        _hint(
            "list_modules",
            "Review reusable modules before adding more checklist items.",
            {"journey_id": journey["id"]},
        )
    ]


def direct_item_hints(
    journey: dict[str, Any], item_ids: list[str], items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    direct = [
        item for item in items if item["id"] in item_ids and item["source"]["kind"] == "direct"
    ]
    if not direct:
        return []
    args: dict[str, Any] = {
        "journey_id": journey["id"],
        "item_ids": [item["id"] for item in direct],
    }
    needs: list[str] = []
    if journey.get("source_blueprint_id"):
        args["blueprint_id"] = journey["source_blueprint_id"]
    else:
        needs.append("blueprint_id or new_blueprint_name")
    hints = [
        _hint(
            "promote_items",
            "These direct items can be remembered in a reusable blueprint.",
            args,
            needs=needs,
            confirmation=True,
        )
    ]
    groups = sorted({item["group"] for item in direct if item["group"]})
    if groups:
        pack_items = [
            {
                key: item[key]
                for key in ("name", "group", "quantity", "unit", "note")
                if item.get(key) is not None
            }
            for item in direct
        ]
        hints.append(
            _hint(
                "create_module",
                "Grouped direct items can be saved as a reusable module.",
                {"name": f"{groups[0]} module", "common_items": pack_items, "variants": []},
                confirmation=True,
            )
        )
    return hints[:2]


def include_module_hints(
    target_type: str,
    target_id: str,
    module_id: str,
    available_variants: list[str],
    variant: str | None,
) -> list[dict[str, Any]]:
    if variant is not None or not available_variants:
        return []
    return [
        _hint(
            "include_module",
            "Choose a module variant explicitly; the server will not infer one.",
            {"target_type": target_type, "target_id": target_id, "module_id": module_id},
            needs=["variant"],
            confirmation=True,
        )
    ]


def composition_hints(
    target_type: str,
    target_id: str,
    unresolved_choices: list[dict[str, Any]],
    *,
    conflicts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    hints = [
        _hint(
            "select_module_option",
            f"Resolve the {choice['label']} choice explicitly.",
            {
                "target_type": target_type,
                "target_id": target_id,
                "selection_id": choice["selection_id"],
                "choice_id": choice["choice_id"],
            },
            needs=["option_key"],
            confirmation=True,
        )
        for choice in unresolved_choices
    ]
    if conflicts:
        hints.append(
            _hint(
                "refresh_composition",
                "Refresh the selected modules after reviewing preserved conflicts.",
                {"target_type": target_type, "target_id": target_id},
                confirmation=True,
            )
        )
    return hints[:3]
