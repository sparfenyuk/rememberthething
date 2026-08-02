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
    assert [hint["tool"] for hint in added["next_steps"]] == ["promote_items", "create_pack"]
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
