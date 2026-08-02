from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ChecklistError(Exception):
    """A user-correctable domain or storage error."""

    def __init__(
        self, message: str, *, code: str = "validation_error", details: Any = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.details is not None:
            result["details"] = self.details
        return result


@dataclass(frozen=True)
class ItemSource:
    kind: str
    source_id: str | None = None
    label: str | None = None
    variant: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "id": self.source_id,
            "label": self.label,
            "variant": self.variant,
        }


def result_envelope(
    summary: str,
    affected: dict[str, Any] | None = None,
    *,
    next_steps: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "summary": summary,
        "affected": affected or {},
        "next_steps": next_steps or [],
    }
    if conflicts:
        result["conflicts"] = conflicts
    return result
