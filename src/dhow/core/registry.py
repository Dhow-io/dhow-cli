"""In-memory and serialized registry representation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

from dhow.core.types import Field


@dataclass(kw_only=True)
class DocTypeEntry:
    """One DocType in the registry."""

    name: str
    version: str = "1"
    fields: dict[str, Field] = dc_field(default_factory=dict)
    workflow: dict[str, Any] | None = None
    controls: list[dict[str, Any]] = dc_field(default_factory=list)
    permissions: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "fields": [f.to_dict() for f in self.fields.values()],
            "workflow": self.workflow,
            "controls": self.controls,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocTypeEntry":
        return cls(
            name=data["name"],
            version=data.get("version", "1"),
            fields={f["name"]: Field.from_dict(f) for f in data.get("fields", [])},
            workflow=data.get("workflow"),
            controls=list(data.get("controls", [])),
            permissions=data.get("permissions", {}),
        )


@dataclass
class Registry:
    """Collection of DocType entries — the runtime source of truth."""

    doctypes: dict[str, DocTypeEntry] = dc_field(default_factory=dict)

    def add(self, entry: DocTypeEntry) -> None:
        self.doctypes[entry.name] = entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "1",
            "doctypes": {name: entry.to_dict() for name, entry in self.doctypes.items()},
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Registry":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            doctypes={
                name: DocTypeEntry.from_dict(entry)
                for name, entry in data.get("doctypes", {}).items()
            }
        )
