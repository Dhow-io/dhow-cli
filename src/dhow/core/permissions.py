"""Declarative permission sets for DocTypes."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

from dhow.core.types import Operation


@dataclass(kw_only=True)
class PermissionSet:
    """Role -> operation mapping for a DocType."""

    grants: dict[str, dict[str, Any]] = dc_field(default_factory=dict)
    field_rules: dict[str, dict[str, Any]] = dc_field(default_factory=dict)

    @classmethod
    def from_decl(cls, decl: dict[str, Any] | None) -> "PermissionSet":
        """Build a permission set from the declarative dict supplied on a DocType."""
        grants: dict[str, dict[str, Any]] = {}
        field_rules: dict[str, dict[str, Any]] = {}
        if not decl:
            return cls(grants=grants, field_rules=field_rules)
        for key, value in decl.items():
            if key.startswith("field_"):
                field_rules[key] = value
            else:
                op = Operation(key) if key in {o.value for o in Operation} else key
                if isinstance(value, str):
                    grants[op.value if isinstance(op, Operation) else op] = {"roles": [value]}
                elif isinstance(value, list):
                    grants[op.value if isinstance(op, Operation) else op] = {"roles": value}
                elif isinstance(value, dict):
                    grants[op.value if isinstance(op, Operation) else op] = value
                else:
                    raise ValueError(f"Invalid permission value for {key}: {value!r}")
        return cls(grants=grants, field_rules=field_rules)

    def to_dict(self) -> dict[str, Any]:
        return {"grants": self.grants, "field_rules": self.field_rules}
