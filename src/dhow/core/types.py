"""Core type definitions used across Dhow."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any


class FieldKind(str, Enum):
    """Canonical field kinds."""

    TEXT = "text"
    INT = "int"
    DECIMAL = "decimal"
    DATE = "date"
    DATETIME = "datetime"
    BOOL = "bool"
    SEQUENCE = "sequence"
    LINK = "link"
    TABLE = "table"
    STATE = "state"
    COMPUTED = "computed"
    JSON = "json"


class Operation(str, Enum):
    """Data access operations."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SUBMIT = "submit"


@dataclass(kw_only=True)
class Field:
    """Declarative field definition collected by the DocType metaclass."""

    name: str | None = None
    kind: FieldKind = FieldKind.TEXT
    required: bool = False
    index: bool = False
    unique: bool = False
    default: Any = None
    immutable: bool = False
    label: str | None = None
    hidden: bool | list[str] | None = None
    read_only: bool | list[str] | None = None
    options: dict[str, Any] = dc_field(default_factory=dict)

    def with_name(self, name: str) -> "Field":
        return Field(
            name=name,
            kind=self.kind,
            required=self.required,
            index=self.index,
            unique=self.unique,
            default=self.default,
            immutable=self.immutable,
            label=self.label or name.replace("_", " ").title(),
            hidden=self.hidden,
            read_only=self.read_only,
            options=dict(self.options),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "required": self.required,
            "index": self.index,
            "unique": self.unique,
            "default": self.default,
            "immutable": self.immutable,
            "label": self.label,
            "hidden": self.hidden,
            "read_only": self.read_only,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Field":
        return cls(
            name=data.get("name"),
            kind=FieldKind(data.get("kind", "text")),
            required=data.get("required", False),
            index=data.get("index", False),
            unique=data.get("unique", False),
            default=data.get("default"),
            immutable=data.get("immutable", False),
            label=data.get("label"),
            hidden=data.get("hidden"),
            read_only=data.get("read_only"),
            options=data.get("options", {}),
        )
