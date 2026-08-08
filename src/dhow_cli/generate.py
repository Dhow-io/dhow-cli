"""`dhow generate-ui` implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dhow.core.project import Project
from dhow.core.registry import Registry
from dhow.generators.ui import generate_ui


def run_generate_ui(project: Project, *, output: Path | None = None) -> dict[str, Any]:
    """Generate the React/TypeScript Desk UI into *output* (default: build/ui)."""
    target = output or project.build_dir / "ui"
    registry = Registry.load(project.registry_path)
    paths = generate_ui(registry, target)
    return {"ok": True, "output": str(target), "files": {k: str(v) for k, v in paths.items()}}
