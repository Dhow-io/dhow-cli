"""`dhow build` and `dhow diff` implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dhow.core.compiler import compile_registry, diff_registry, emit_all
from dhow.core.project import Project
from dhow.core.registry import Registry


def run_build(project: Project, *, check: bool = False) -> dict[str, Any]:
    """Compile project DocTypes and emit all artifacts.

    When `check=True`, compares the emitted registry with the existing one and
    returns a drift report without writing files.
    """
    doctypes = project.load_doctypes()
    new_registry = compile_registry(doctypes)

    old_registry = Registry.load(project.registry_path)
    drift = diff_registry(old_registry, new_registry)
    has_drift = bool(drift["added"] or drift["removed"] or drift["changed"])

    if check:
        return {"ok": not has_drift, "drift": drift}

    paths = emit_all(new_registry, project.build_dir, registry_path=project.registry_path)
    return {"ok": True, "drift": drift, "paths": {k: str(v) for k, v in paths.items()}}


def run_diff(project: Project) -> dict[str, Any]:
    """Compute pending schema changes without writing files."""
    doctypes = project.load_doctypes()
    new_registry = compile_registry(doctypes)
    old_registry = Registry.load(project.registry_path)
    return diff_registry(old_registry, new_registry)
