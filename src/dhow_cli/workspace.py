"""Dhow workspace and app discovery.

A workspace is a directory that contains an ``apps/`` folder of Dhow apps,
a ``sites/`` folder with an ``apps.txt`` manifest, and a top-level
``dhow.toml`` site config. The CLI uses this module to discover installed
apps and load their per-app contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import toml

DEFAULT_APPS = ["dhow"]


@dataclass(frozen=True)
class AppContract:
    """Parsed ``dhow.toml`` contract for one installed app."""

    app_name: str
    title: str
    version: str
    publisher: str
    description: str
    license: str
    framework_version: str
    modules: dict[str, str]
    commands: dict[str, str]
    hooks: dict[str, list[str]]
    doctypes: dict[str, str]
    raw: dict[str, Any]
    path: Path
    source_path: Path


@dataclass(frozen=True)
class Workspace:
    """Discovered Dhow workspace."""

    root: Path
    apps_path: Path
    sites_path: Path
    config_path: Path
    apps: list[str]
    app_contracts: dict[str, AppContract]

    def get_app_contract(self, name: str) -> AppContract | None:
        return self.app_contracts.get(name)


def discover_workspace(path: Path | None = None) -> Workspace | None:
    """Walk upward from ``path`` (or CWD) looking for a Dhow workspace.

    A workspace is identified by the presence of ``apps/`` and ``sites/``.
    If neither is found, return ``None``.
    """
    cwd = path or Path.cwd()
    check = cwd
    while True:
        apps_dir = check / "apps"
        sites_dir = check / "sites"
        if apps_dir.is_dir() and sites_dir.is_dir():
            return _load_workspace(check)
        parent = check.parent
        if parent == check:
            return None
        check = parent


def _load_workspace(root: Path) -> Workspace:
    apps_path = root / "apps"
    sites_path = root / "sites"
    config_path = root / "dhow.toml"

    apps = _read_apps_list(sites_path / "apps.txt")
    if "dhow" not in apps:
        apps.insert(0, "dhow")

    contracts: dict[str, AppContract] = {}
    for app_name in apps:
        app_source = apps_path / app_name
        contract_path = app_source / "dhow.toml"
        if not contract_path.is_file():
            continue
        contract = _parse_contract(app_name, app_source, contract_path)
        if contract:
            contracts[app_name] = contract

    return Workspace(
        root=root,
        apps_path=apps_path,
        sites_path=sites_path,
        config_path=config_path if config_path.is_file() else None,  # type: ignore[arg-type]
        apps=apps,
        app_contracts=contracts,
    )


def _read_apps_list(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _parse_contract(app_name: str, source_path: Path, path: Path) -> AppContract | None:
    try:
        raw = toml.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    app_section = raw.get("app", {})
    framework_section = raw.get("framework", {})
    modules = raw.get("modules", {})
    commands = raw.get("commands", {})
    hooks = raw.get("hooks", {})
    doctypes = raw.get("doctypes", {})

    return AppContract(
        app_name=app_section.get("name", app_name),
        title=app_section.get("title", app_name),
        version=app_section.get("version", "0.0.0"),
        publisher=app_section.get("publisher", ""),
        description=app_section.get("description", ""),
        license=app_section.get("license", ""),
        framework_version=framework_section.get("version", "*"),
        modules={str(k): str(v) for k, v in modules.items()},
        commands={str(k): str(v) for k, v in commands.items()},
        hooks={str(k): list(v) if isinstance(v, list) else [str(v)] for k, v in hooks.items()},
        doctypes={str(k): str(v) for k, v in doctypes.items()},
        raw=raw,
        path=path,
        source_path=source_path,
    )


def write_apps_list(workspace: Workspace, apps: list[str]) -> None:
    """Persist the ordered list of installed apps."""
    path = workspace.sites_path / "apps.txt"
    workspace.sites_path.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(apps) + "\n", encoding="utf-8")
