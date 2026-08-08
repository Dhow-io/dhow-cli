"""Declarative data integrity controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(kw_only=True)
class ImmutableAfter:
    """Disallow UPDATE/DELETE once the state field reaches one of these values."""

    state_field: str
    values: list[str]

    def __init__(self, state_field: str, values: list[str] | None = None):
        self.state_field = state_field
        self.values = values if values is not None else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "immutable_after",
            "state_field": self.state_field,
            "values": self.values,
        }
