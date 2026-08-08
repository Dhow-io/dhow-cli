"""Load and register per-app commands from installed Dhow apps.

Mirrors ``frappe.utils.bench_helper.get_app_commands``.
"""

from __future__ import annotations

import importlib
import traceback
from typing import Any

import typer

from dhow_cli.workspace import Workspace


def load_app_commands(workspace: Workspace) -> dict[str, typer.Typer]:
    """Return a Typer sub-app for each installed app that exposes commands."""
    groups: dict[str, typer.Typer] = {}
    for app_name in workspace.apps:
        contract = workspace.get_app_contract(app_name)
        if not contract:
            continue
        if not contract.commands:
            continue

        app_typer = typer.Typer(help=f"{contract.title} commands")
        for command_name, import_path in contract.commands.items():
            _register_command(app_typer, command_name, import_path)

        if app_typer.registered_groups or app_typer.registered_commands:
            groups[app_name] = app_typer

    return groups


def _register_command(app_typer: typer.Typer, name: str, import_path: str) -> None:
    """Attach a command function loaded from ``module.path:function_name``."""
    try:
        module_path, func_name = import_path.rsplit(":", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
    except Exception:
        traceback.print_exc()
        return

    @app_typer.command(name)
    def _cmd(
        json: bool = typer.Option(False, "--json", help="Emit JSON output"),
    ) -> None:
        try:
            result = func()
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        if json:
            import json as _json

            typer.echo(_json.dumps(result, indent=2, default=str))
        else:
            for key, value in result.items():
                typer.echo(f"{key}: {value}")

    # Stash the original import path for debugging.
    _cmd.__dhow_command_target = import_path  # type: ignore[attr-defined]


def run_hook(workspace: Workspace, hook_name: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run every callback registered for ``hook_name`` across installed apps."""
    results: list[dict[str, Any]] = []
    ctx = context or {}
    for app_name in workspace.apps:
        contract = workspace.get_app_contract(app_name)
        if not contract:
            continue
        for target in contract.hooks.get(hook_name, []):
            try:
                module_path, func_name = target.rsplit(":", 1)
                module = importlib.import_module(module_path)
                func = getattr(module, func_name)
                results.append(
                    {
                        "app": app_name,
                        "hook": hook_name,
                        "target": target,
                        "result": func(ctx),
                    }
                )
            except Exception as exc:
                traceback.print_exc()
                results.append(
                    {
                        "app": app_name,
                        "hook": hook_name,
                        "target": target,
                        "error": str(exc),
                    }
                )
    return results
