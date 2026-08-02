from __future__ import annotations

import pytest

from src.journey_checklist.models import ChecklistError
from src.journey_checklist.repository import Repository


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "journey.sqlite3")


def test_blueprint_snapshot_and_explicit_promotion(repository):
    blueprint = repository.create_blueprint("business trip", [{"name": "passport"}])
    journey = repository.start_journey(
        "Berlin", {"destination": "Berlin", "season": "winter"}, blueprint["id"]
    )
    copied = journey["items"][0]
    assert copied["source"]["kind"] == "blueprint"
    assert repository.remove_items("journey", journey["id"], [copied["id"]])
    assert repository.get_blueprint(blueprint["id"])["item_count"] == 1

    added = repository.add_items(
        "journey", journey["id"], [{"name": "umbrella", "group": "weather"}]
    )
    promoted = repository.promote_items(
        journey["id"], added["item_ids"], blueprint_id=blueprint["id"]
    )
    assert promoted["blueprint"]["item_count"] == 2
    assert repository.get_journey(journey["id"])["item_count"] == 1


def test_pack_variants_are_snapshots_and_preserve_duplicates(repository):
    journey = repository.start_journey("Vacation", {"season": "winter"})
    repository.add_items("journey", journey["id"], [{"name": "toothbrush", "note": "edited"}])
    item = repository.get_journey(journey["id"])["items"][0]
    repository.update_items(
        "journey", journey["id"], [{"item_id": item["id"], "note": "keep mine"}]
    )
    pack = repository.create_pack(
        "vacation",
        [{"name": "toothbrush"}, {"name": "sunscreen"}],
        [
            {"label": "winter", "items": [{"name": "wool hat"}]},
            {"label": "summer", "items": [{"name": "swimsuit"}]},
        ],
    )
    included = repository.include_pack("journey", journey["id"], pack["id"], "winter")
    assert included["added_item_ids"]
    assert [item["name"] for item in included["target"]["items"]] == [
        "toothbrush",
        "sunscreen",
        "wool hat",
    ]
    assert included["conflicts"][0]["existing_item_id"] == item["id"]
    repository.delete_pack(pack["id"])
    assert repository.get_journey(journey["id"])["item_count"] == 3


def test_unknown_bulk_update_has_no_partial_write(repository):
    journey = repository.start_journey("Trip")
    added = repository.add_items(
        "journey", journey["id"], [{"name": "passport"}, {"name": "wallet"}]
    )
    with pytest.raises(ChecklistError):
        repository.update_items(
            "journey",
            journey["id"],
            [
                {"item_id": added["item_ids"][0], "packed": True},
                {"item_id": "missing", "packed": True},
            ],
        )
    assert not repository.get_journey(journey["id"])["items"][0]["packed"]


def test_restart_persistence(repository):
    journey = repository.start_journey("Persistent")
    repository.add_items("journey", journey["id"], [{"name": "charger"}])
    restarted = Repository(repository.path)
    assert restarted.get_journey(journey["id"])["items"][0]["name"] == "charger"
