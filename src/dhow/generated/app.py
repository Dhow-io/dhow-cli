"""Default generated FastAPI app — loads registry from disk."""

from __future__ import annotations

from pathlib import Path

from dhow.core.project import Project
from dhow.core.registry import Registry
from dhow.generators.api import create_app

project = Project(Path.cwd())
registry = Registry.load(project.registry_path)
app = create_app(registry)
