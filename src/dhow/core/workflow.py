"""Workflow primitives for DocType definitions."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any


@dataclass(kw_only=True)
class Approval:
    """Approval gate mapped by predicates."""

    threshold: dict[str, str] = dc_field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.threshold, dict) and len(self.threshold) == 0:
            # Default universal threshold
            self.threshold = {"true": "manager"}

    @property
    def thresholds(self) -> dict[str, str]:
        return self.threshold

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "approval", "thresholds": self.threshold}


@dataclass(kw_only=True)
class StateMachine:
    """State machine workflow with allowed transitions."""

    states: list[str] = dc_field(default_factory=list)
    transitions: dict[str, list[str]] = dc_field(default_factory=dict)
    initial: str | None = None

    def __post_init__(self) -> None:
        if self.initial is None and self.states:
            self.initial = self.states[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "state_machine",
            "states": self.states,
            "transitions": self.transitions,
            "initial": self.initial,
        }


class Workflow:
    """Namespace object exposed as `dhow.workflow` so both
    `workflow.Approval(...)` and `workflow = workflow.Approval(...)` work.
    """

    Approval = Approval
    StateMachine = StateMachine
