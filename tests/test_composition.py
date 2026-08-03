from __future__ import annotations

import sqlite3

import pytest

from src.journey_checklist.models import ChecklistError
from src.journey_checklist.repository import Repository


def test_module_keys_deltas_and_nested_provenance(tmp_path):
    repository = Repository(tmp_path / "modules.sqlite3")
    everyday = repository.create_module(
        "Everyday",
        [{"item_key": "passport", "name": "Passport"}, {"item_key": "macbook", "name": "MacBook"}],
        variants=[
            {
                "label": "car",
                "add": [{"item_key": "car-docs", "name": "Car documents"}],
                "remove": ["passport"],
            }
        ],
    )
    car = repository.create_module("Car", [{"item_key": "keys", "name": "Keys"}])
    roadtrip = repository.create_module("Roadtrip", includes=[everyday["id"], car["id"]])
    journey = repository.start_journey("Roadtrip")

    included = repository.include_module("journey", journey["id"], roadtrip["id"])
    assert [item["name"] for item in included["target"]["items"]] == ["Passport", "MacBook", "Keys"]
    assert included["target"]["items"][0]["source"]["path"] == ["Roadtrip", "Everyday"]

    repository.update_module(
        everyday["id"],
        common_items=[
            {"item_key": "passport", "name": "Travel passport"},
            {"item_key": "macbook", "name": "MacBook"},
        ],
    )
    updated = repository.get_module(everyday["id"])
    assert updated["items"][0]["item_key"] == "passport"
    assert (
        repository.include_module("journey", journey["id"], everyday["id"], variant="car")[
            "target"
        ]["items"][-1]["name"]
        == "Car documents"
    )


def test_nested_cycle_is_rejected_without_changing_edges(tmp_path):
    repository = Repository(tmp_path / "cycles.sqlite3")
    first = repository.create_module("First")
    second = repository.create_module("Second", includes=[first["id"]])

    with pytest.raises(ChecklistError, match="cycle"):
        repository.update_module(first["id"], includes=[second["id"]])

    assert repository.get_module(first["id"])["includes"] == []


def test_refresh_preserves_edits_and_durable_removals(tmp_path):
    repository = Repository(tmp_path / "refresh.sqlite3")
    module = repository.create_module("Weather", [{"item_key": "coat", "name": "Coat"}])
    journey = repository.start_journey("Trip")
    included = repository.include_module("journey", journey["id"], module["id"])
    coat_id = included["target"]["items"][0]["id"]
    repository.update_items("journey", journey["id"], [{"item_id": coat_id, "name": "My coat"}])
    repository.remove_items("journey", journey["id"], [coat_id])
    repository.update_module(
        module["id"],
        common_items=[
            {"item_key": "coat", "name": "Updated coat"},
            {"item_key": "umbrella", "name": "Umbrella"},
        ],
    )

    refreshed = repository.refresh_composition("journey", journey["id"])
    assert [item["name"] for item in refreshed["target"]["items"]] == ["Umbrella"]


def test_refresh_reports_edited_source_conflict(tmp_path):
    repository = Repository(tmp_path / "conflicts.sqlite3")
    module = repository.create_module("Work", [{"item_key": "laptop", "name": "Laptop"}])
    journey = repository.start_journey("Trip")
    included = repository.include_module("journey", journey["id"], module["id"])
    item_id = included["target"]["items"][0]["id"]
    repository.update_items("journey", journey["id"], [{"item_id": item_id, "note": "keep this"}])
    repository.update_module(
        module["id"], common_items=[{"item_key": "laptop", "name": "New laptop"}]
    )

    refreshed = repository.refresh_composition("journey", journey["id"])
    assert refreshed["conflicts"][0]["reason"] == "edited_target_preserved"
    assert refreshed["target"]["items"][0]["name"] == "Laptop"


def test_refresh_reports_duplicate_name_when_source_key_exists(tmp_path):
    repository = Repository(tmp_path / "duplicate-name.sqlite3")
    module = repository.create_module("Work", [{"item_key": "coat", "name": "Coat"}])
    journey = repository.start_journey("Trip")
    repository.add_items("journey", journey["id"], [{"name": "Umbrella"}])
    repository.include_module("journey", journey["id"], module["id"])
    repository.update_module(
        module["id"], common_items=[{"item_key": "coat", "name": "Umbrella"}]
    )

    refreshed = repository.refresh_composition("journey", journey["id"])
    assert refreshed["conflicts"][0]["reason"] == "duplicate_name_preserved"
    assert [item["name"] for item in refreshed["target"]["items"]] == ["Umbrella", "Coat"]


def test_refresh_updates_name_index_before_next_source_key(tmp_path):
    repository = Repository(tmp_path / "duplicate-refresh.sqlite3")
    module = repository.create_module(
        "Work",
        [
            {"item_key": "first", "name": "First"},
            {"item_key": "second", "name": "Second"},
        ],
    )
    journey = repository.start_journey("Trip")
    repository.include_module("journey", journey["id"], module["id"])
    repository.update_module(
        module["id"],
        common_items=[
            {"item_key": "first", "name": "Same"},
            {"item_key": "second", "name": "Same"},
        ],
    )

    refreshed = repository.refresh_composition("journey", journey["id"])
    assert refreshed["conflicts"][0]["reason"] == "duplicate_name_preserved"
    assert [item["name"] for item in refreshed["target"]["items"]] == ["Same", "Second"]


def test_module_update_requires_stable_item_keys(tmp_path):
    repository = Repository(tmp_path / "stable-keys.sqlite3")
    module = repository.create_module("Work", [{"item_key": "old-key", "name": "Old"}])

    with pytest.raises(ChecklistError, match="requires item_key"):
        repository.update_module(module["id"], common_items=[{"name": "Renamed"}])

    assert repository.get_module(module["id"])["items"][0]["item_key"] == "old-key"


def test_module_update_rejects_invalidating_selected_variant(tmp_path):
    repository = Repository(tmp_path / "stale-selection.sqlite3")
    module = repository.create_module(
        "Travel", variants=[{"label": "car", "add": [{"name": "Keys"}]}]
    )
    journey = repository.start_journey("Trip")
    repository.include_module("journey", journey["id"], module["id"], variant="car")

    with pytest.raises(ChecklistError, match="invalidate"):
        repository.update_module(module["id"], variants=[])

    assert [item["name"] for item in repository.get_journey(journey["id"])["items"]] == ["Keys"]


def test_one_of_is_unresolved_until_selected(tmp_path):
    repository = Repository(tmp_path / "choices.sqlite3")
    module = repository.create_module(
        "Video",
        choices=[
            {
                "choice_key": "lens",
                "label": "Lens",
                "options": [
                    {"option_key": "zoom", "name": "24-70"},
                    {"option_key": "prime", "name": "35mm"},
                ],
            }
        ],
    )
    journey = repository.start_journey("Trip")
    included = repository.include_module("journey", journey["id"], module["id"])
    assert included["unresolved_choices"][0]["choice_key"] == "lens"
    assert included["target"]["items"] == []

    selected = repository.select_module_option(
        "journey",
        journey["id"],
        "lens",
        "prime",
        included["selection_id"],
    )
    assert [item["name"] for item in selected["target"]["items"]] == ["35mm"]
    assert selected["target"]["unresolved_choices"] == []


def test_switching_an_edited_choice_is_rejected(tmp_path):
    repository = Repository(tmp_path / "edited-choice.sqlite3")
    module = repository.create_module(
        "Video",
        choices=[
            {
                "choice_key": "lens",
                "label": "Lens",
                "options": [
                    {"option_key": "prime", "name": "35mm"},
                    {"option_key": "zoom", "name": "24-70"},
                ],
            }
        ],
    )
    journey = repository.start_journey("Trip")
    included = repository.include_module("journey", journey["id"], module["id"])
    selected = repository.select_module_option(
        "journey", journey["id"], "lens", "prime", included["selection_id"]
    )
    repository.update_items(
        "journey", journey["id"], [{"item_id": selected["target"]["items"][0]["id"], "note": "keep"}]
    )

    with pytest.raises(ChecklistError, match="editing its selected item"):
        repository.select_module_option(
            "journey", journey["id"], "lens", "zoom", included["selection_id"]
        )

    assert [item["name"] for item in repository.get_journey(journey["id"])["items"]] == ["35mm"]


def test_nested_choice_can_be_included_and_selected(tmp_path):
    repository = Repository(tmp_path / "nested-choices.sqlite3")
    child = repository.create_module(
        "Video",
        choices=[
            {
                "choice_key": "lens",
                "label": "Lens",
                "options": [{"option_key": "prime", "name": "35mm"}],
            }
        ],
    )
    parent = repository.create_module("Camera kit", includes=[child["id"]])
    journey = repository.start_journey("Trip")

    included = repository.include_module("journey", journey["id"], parent["id"])
    choice = included["unresolved_choices"][0]
    selected = repository.select_module_option(
        "journey", journey["id"], choice["choice_id"], "prime", included["selection_id"]
    )

    assert [item["name"] for item in selected["target"]["items"]] == ["35mm"]
    assert selected["target"]["unresolved_choices"] == []

    second = repository.start_journey("Second trip")
    explicit = repository.include_module(
        "journey",
        second["id"],
        parent["id"],
        choices=[{"choice_id": child["choices"][0]["id"], "option_key": "prime"}],
    )
    assert [item["name"] for item in explicit["target"]["items"]] == ["35mm"]


def test_legacy_pack_migration_is_idempotent(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    repository = Repository(path)
    repository.create_pack(
        "legacy",
        [{"name": "Passport"}, {"name": "Wallet"}],
        [{"label": "car", "items": [{"name": "Keys"}]}],
    )

    first = repository.list_modules()
    second = Repository(path).list_modules()
    assert len(first) == len(second) == 1
    module = Repository(path).get_module(first[0]["id"])
    assert module["variants"][0]["add"][0]["item_key"] == "keys"
    assert module["variants"][0]["remove"] == ["passport", "wallet"]


def test_legacy_migration_separates_common_and_variant_keys(tmp_path):
    path = tmp_path / "legacy-collision.sqlite3"
    repository = Repository(path)
    repository.create_pack(
        "legacy",
        [{"name": "a-b"}],
        [{"label": "variant", "items": [{"name": "a/b"}]}],
    )

    migrated = Repository(path)
    module = migrated.get_module(migrated.list_modules()[0]["id"])
    assert module["variants"][0]["add"][0]["item_key"] == "a-b-2"
    journey = migrated.start_journey("Trip")
    included = migrated.include_module(
        "journey", journey["id"], module["id"], variant="variant"
    )
    assert [item["name"] for item in included["target"]["items"]] == ["a/b"]


def test_legacy_migration_renames_conflicting_module_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy-name-conflict.sqlite3"
    repository = Repository(path)
    repository.create_module("legacy")
    repository.create_pack("legacy", [{"name": "Passport"}])

    migrated = [module for module in repository.list_modules() if module["name"] != "legacy"]
    assert len(migrated) == 1
    module = repository.get_module(migrated[0]["id"])
    assert module["items"][0]["name"] == "Passport"
    with sqlite3.connect(path) as connection:
        first_count = connection.execute("SELECT COUNT(*) FROM migration_diagnostics").fetchone()[0]
    Repository(path).list_modules()
    with sqlite3.connect(path) as connection:
        second_count = connection.execute(
            "SELECT COUNT(*) FROM migration_diagnostics"
        ).fetchone()[0]
    assert first_count == second_count == 1


def test_module_schema_has_no_deferred_rule_columns(tmp_path):
    repository = Repository(tmp_path / "schema.sqlite3")
    with sqlite3.connect(repository.path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(modules)").fetchall()}
    assert "conditions" not in columns
    assert "computed_quantity" not in columns
