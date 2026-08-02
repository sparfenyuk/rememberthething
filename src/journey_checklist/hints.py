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


def journey_hints(journey: dict[str, Any], packs: dict[str, Any]) -> list[dict[str, Any]]:
    if any(item["source"]["kind"] == "pack" for item in journey["items"]):
        return []
    if not packs["packs"]:
        return []
    has_variants = any(pack["variants"] for pack in packs["packs"])
    needs = ["season"] if has_variants and not journey["context"].get("season") else []
    return [
        _hint(
            "list_packs",
            "Review reusable packs before adding more checklist items.",
            {"journey_id": journey["id"]},
            needs=needs,
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
                "create_pack",
                "Grouped direct items can be saved as a reusable pack.",
                {"name": f"{groups[0]} pack", "common_items": pack_items, "variants": []},
                confirmation=True,
            )
        )
    return hints[:2]


def include_pack_hints(
    target_type: str,
    target_id: str,
    pack_id: str,
    available_variants: list[str],
    variant: str | None,
) -> list[dict[str, Any]]:
    if variant is not None or not available_variants:
        return []
    return [
        _hint(
            "include_pack",
            "Choose a pack variant explicitly; the server will not infer one.",
            {"target_type": target_type, "target_id": target_id, "pack_id": pack_id},
            needs=["variant"],
            confirmation=True,
        )
    ]
