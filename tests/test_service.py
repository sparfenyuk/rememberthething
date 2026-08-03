from __future__ import annotations

import pytest

from src.journey_checklist.models import ChecklistError
from src.journey_checklist.repository import Repository
from src.journey_checklist.service import ChecklistService, run_tool


def test_service_envelope_hints_are_bounded_and_non_chaining(tmp_path):
    service = ChecklistService(Repository(tmp_path / "service.sqlite3"))
    journey = service.start_journey("Trip")["affected"]["journey"]
    added = service.add_items("journey", journey["id"], [{"name": "umbrella", "group": "weather"}])
    assert added["summary"] == "Items added."
    assert [hint["tool"] for hint in added["next_steps"]] == ["promote_items", "create_module"]
    assert all("requires_confirmation" in hint for hint in added["next_steps"])
    assert service.get_journey(journey["id"])["affected"]["journey"]["item_count"] == 1


def test_service_rejects_unknown_target_without_mutation(tmp_path):
    service = ChecklistService(Repository(tmp_path / "service.sqlite3"))
    with pytest.raises(ChecklistError, match="Unknown journey id: missing"):
        service.update_items("journey", "missing", [{"item_id": "missing", "packed": True}])

    result, is_error = run_tool(
        lambda: service.update_items("journey", "missing", [{"item_id": "missing", "packed": True}])
    )
    assert is_error is True
    assert result["error"]["code"] == "not_found"
    assert result["next_steps"] == []


def test_season_hint_targets_update_journey(tmp_path):
    service = ChecklistService(Repository(tmp_path / "service.sqlite3"))
    service.create_pack("seasonal", [], [{"label": "winter", "items": [{"name": "coat"}]}])
    journey = service.start_journey("Trip")["affected"]["journey"]
    hint = service.update_journey(journey["id"], {})["next_steps"][0]
    assert hint["tool"] == "update_journey"
    assert hint["arguments"] == {"journey_id": journey["id"]}
    assert hint["needs"] == ["season"]
    updated = service.update_journey(journey["id"], {"season": "winter"})
    assert updated["next_steps"][0]["tool"] == "list_modules"


def test_initial_composition_hints_expose_choice_selection(tmp_path):
    service = ChecklistService(Repository(tmp_path / "initial-choice-hints.sqlite3"))
    module = service.repository.create_module(
        "Video",
        choices=[
            {
                "choice_key": "lens",
                "label": "Lens",
                "options": [{"option_key": "prime", "name": "35mm"}],
            }
        ],
    )

    blueprint = service.create_blueprint("Camera", module_selections=[module["id"]])
    journey = service.start_journey("Trip", module_selections=[module["id"]])

    assert blueprint["next_steps"][0]["tool"] == "select_module_option"
    assert journey["next_steps"][0]["tool"] == "select_module_option"


def test_initial_composition_hints_update_selected_variant(tmp_path):
    service = ChecklistService(Repository(tmp_path / "initial-variant-hints.sqlite3"))
    module = service.repository.create_module(
        "Packing",
        [{"item_key": "base", "name": "Base"}],
        variants=[{"label": "alt", "add": [{"item_key": "extra", "name": "Extra"}]}],
    )

    blueprint = service.create_blueprint("Trip", module_selections=[module["id"]])
    journey = service.start_journey("Trip", module_selections=[module["id"]])

    for result, target_name in ((blueprint, "blueprint"), (journey, "journey")):
        target = result["affected"][target_name]
        hint = result["next_steps"][0]
        assert hint["tool"] == "include_module"
        assert hint["arguments"] == {
            "target_type": target_name,
            "target_id": target["id"],
            "module_id": module["id"],
            "selection_id": target["selected_modules"][0]["selection_id"],
        }
        assert hint["needs"] == ["variant"]


def test_current_composition_hint_precedes_older_variant_suggestions(tmp_path):
    service = ChecklistService(Repository(tmp_path / "composition-hint-priority.sqlite3"))
    previous = [
        service.repository.create_module(
            f"Previous {index}", variants=[{"label": "alt", "add": []}]
        )
        for index in range(3)
    ]
    journey = service.start_journey("Trip")["affected"]["journey"]
    for module in previous:
        service.include_module("journey", journey["id"], module["id"])

    choices = service.repository.create_module(
        "Video",
        choices=[
            {
                "choice_key": "lens",
                "label": "Lens",
                "options": [{"option_key": "prime", "name": "35mm"}],
            }
        ],
    )
    selected_choice = service.include_module("journey", journey["id"], choices["id"])
    assert selected_choice["next_steps"][0]["tool"] == "select_module_option"
    assert (
        selected_choice["next_steps"][0]["arguments"]["selection_id"]
        == selected_choice["affected"]["selection_id"]
    )

    variants = service.repository.create_module("Current", variants=[{"label": "alt", "add": []}])
    selected_variant = service.include_module("journey", journey["id"], variants["id"])
    assert selected_variant["next_steps"][0]["tool"] == "include_module"
    assert (
        selected_variant["next_steps"][0]["arguments"]["selection_id"]
        == selected_variant["affected"]["selection_id"]
    )
    assert any(hint["tool"] == "select_module_option" for hint in selected_variant["next_steps"])
    assert len(selected_variant["next_steps"]) == 3


def test_creation_conflicts_are_returned_for_blueprints_and_journeys(tmp_path):
    service = ChecklistService(Repository(tmp_path / "creation-conflicts.sqlite3"))
    module = service.repository.create_module(
        "Packing", [{"item_key": "passport", "name": "Passport"}]
    )

    blueprint = service.create_blueprint("Trip", [{"name": "Passport"}], [module["id"]])
    assert blueprint["conflicts"][0]["reason"] == "duplicate_name_preserved"
    blueprint_id = blueprint["affected"]["blueprint"]["id"]

    journey = service.start_journey("Trip", blueprint_id=blueprint_id)
    assert journey["conflicts"][0]["reason"] == "duplicate_name_preserved"


def test_include_module_variant_hint_updates_existing_selection(tmp_path):
    service = ChecklistService(Repository(tmp_path / "variant-hints.sqlite3"))
    module = service.repository.create_module(
        "Packing",
        [{"item_key": "base", "name": "Base"}],
        variants=[{"label": "alt", "add": [{"item_key": "extra", "name": "Extra"}]}],
    )
    journey = service.start_journey("Trip")["affected"]["journey"]

    included = service.include_module("journey", journey["id"], module["id"])
    hint = included["next_steps"][0]
    assert hint["tool"] == "include_module"
    assert hint["arguments"]["selection_id"] == included["affected"]["selection_id"]

    updated = service.include_module(
        "journey",
        journey["id"],
        module["id"],
        variant="alt",
        selection_id=hint["arguments"]["selection_id"],
    )
    assert updated.get("conflicts", []) == []
    assert [item["name"] for item in updated["affected"]["target"]["items"]] == [
        "Base",
        "Extra",
    ]
    assert updated["affected"]["target"]["items"][0]["source"]["variant"] == "alt"
    assert len(updated["affected"]["target"]["selected_modules"]) == 1
