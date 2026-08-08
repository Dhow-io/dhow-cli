"""Project configuration and module loading."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import toml

from dhow.core.doctype import DocType


class Project:
    """Represents a Dhow project on disk."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config_path = self.root / "dhow.toml"
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        if self.config_path.exists():
            return toml.loads(self.config_path.read_text(encoding="utf-8"))
        return {"project": {}, "build": {}}

    def _resolve_path(self, key: str, default: Path) -> Path:
        raw = self.config.get("build", {}).get(key)
        path = Path(raw) if raw else default
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    @property
    def build_dir(self) -> Path:
        return self._resolve_path("output_dir", self.root / "build")

    @property
    def registry_path(self) -> Path:
        return self._resolve_path(
            "registry_path", self.root / "migrations" / "dhow_registry.json"
        )

    def load_doctypes(self) -> list[type[DocType]]:
        """Import every Python module under modules/doctypes and collect DocTypes."""
        doctypes_dir = self.root / "modules" / "doctypes"
        if not doctypes_dir.exists():
            return []
        collected: list[type[DocType]] = []
        for path in sorted(doctypes_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module_name = f"dhow_project.doctypes.{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            for obj in vars(module).values():
                if isinstance(obj, type) and issubclass(obj, DocType) and obj is not DocType:
                    collected.append(obj)
        return collected
