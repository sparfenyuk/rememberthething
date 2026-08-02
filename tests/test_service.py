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


def test_creation_conflicts_are_returned_for_blueprints_and_journeys(tmp_path):
    service = ChecklistService(Repository(tmp_path / "creation-conflicts.sqlite3"))
    module = service.repository.create_module(
        "Packing", [{"item_key": "passport", "name": "Passport"}]
    )

    blueprint = service.create_blueprint(
        "Trip", [{"name": "Passport"}], [module["id"]]
    )
    assert blueprint["conflicts"][0]["reason"] == "duplicate_name_preserved"
    blueprint_id = blueprint["affected"]["blueprint"]["id"]

    journey = service.start_journey("Trip", blueprint_id=blueprint_id)
    assert journey["conflicts"][0]["reason"] == "duplicate_name_preserved"


def test_include_module_does_not_hint_a_second_variant_selection(tmp_path):
    service = ChecklistService(Repository(tmp_path / "variant-hints.sqlite3"))
    module = service.repository.create_module(
        "Packing",
        [{"item_key": "base", "name": "Base"}],
        variants=[{"label": "alt", "add": [{"item_key": "extra", "name": "Extra"}]}],
    )
    journey = service.start_journey("Trip")["affected"]["journey"]

    included = service.include_module("journey", journey["id"], module["id"])
    assert included["next_steps"] == []
