"""`dhow new module` and `dhow new doctype` implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dhow.core.project import Project


def new_module(project: Project, name: str) -> dict[str, Any]:
    """Create a new module directory under modules/."""
    module_dir = project.root / "modules" / name
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "__init__.py").touch()
    (module_dir / "doctypes").mkdir(parents=True, exist_ok=True)
    (module_dir / "doctypes" / "__init__.py").touch()
    return {"ok": True, "module": name, "path": str(module_dir)}


