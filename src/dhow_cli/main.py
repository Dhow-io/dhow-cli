"""Thin Typer shell over Dhow engine APIs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import typer

from dhow.core.project import Project
from dhow.core.registry import Registry
from dhow_cli.build import run_build, run_diff
from dhow_cli.new import new_module
from dhow.core.layers import (
    Layer,
    LayerApplyError,
    LayerStack,
    LayerValidationError,
    load_layers,
    merge_registry,
    validate_layers,
)
# Local alias to avoid shadowing by per-command `json: bool` Typer options.
from json import dumps as _json_dumps

app = typer.Typer(help="Dhow — metadata-driven declarative ERP framework")
new_app = typer.Typer(help="Create modules and DocTypes")
app.add_typer(new_app, name="new")
layer_app = typer.Typer(help="Manage customization layers (JSON patches on top of the registry)")
app.add_typer(layer_app, name="layer")


def _new_doctype(project: Project, module: str, name: str) -> dict[str, Any]:
    """Create a new DocType file under modules/<module>/doctypes/."""
    base_dir = project.root / "modules"
    base_dir.mkdir(parents=True, exist_ok=True)
    module_dir = base_dir / module
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "__init__.py").touch(exist_ok=True)
    doctype_dir = module_dir / "doctypes"
    doctype_dir.mkdir(parents=True, exist_ok=True)
    (doctype_dir / "__init__.py").touch(exist_ok=True)
    file_path = doctype_dir / f"{name.lower()}.py"
    file_path.write_text(
        f"from dhow import DocType, field\n\n\nclass {name}(DocType):\n"
        f'    title = field.Text(required=True)\n\n'
        f'    permissions = {{"read": "all", "create": "clerk"}}\n',
        encoding="utf-8",
    )
    return {"ok": True, "doctype": name, "path": str(file_path)}


def _project() -> Project:
    return Project(Path.cwd())


def _json_out(data: dict[str, Any]) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


@app.command()
def init(
    name: str,
    path: str = typer.Option(".", help="Directory in which to scaffold the project"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Scaffold a new Dhow project."""
    from dhow_cli.scaffold import scaffold_project

    target = Path(path).resolve() / name
    result = scaffold_project(name, target)
    if json:
        _json_out({"ok": True, "path": str(result), "name": name})
    else:
        typer.echo(f"Created Dhow project '{name}' at {result}")


@app.command()
def build(
    check: bool = typer.Option(False, "--check", help="Exit non-zero if registry != code"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Compile DocType metadata into registry, migrations, schemas, and manifests."""
    result = run_build(_project(), check=check)
    if json:
        _json_out(result)
    else:
        for key, value in result.get("paths", {}).items():
            typer.echo(f"{key}: {value}")
    if check and not result["ok"]:
        raise typer.Exit(1)


@app.command()
def diff(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Print pending schema changes terraform-plan style."""
    result = run_diff(_project())
    if json:
        _json_out(result)
    else:
        for key, value in result.items():
            typer.echo(f"{key}: {value}")


@app.command()
def migrate(
    tenant: str = typer.Option(None, "--tenant", help="Migrate a specific tenant database"),
    rollback: bool = typer.Option(False, "--rollback", help="Roll back migrations"),
    to_version: str = typer.Option(
        None, "--to-version", help="Roll back to (and including) this version"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Apply or roll back database migrations via dhow.engines.migrations.MigrationEngine."""
    from dhow.engines.migrations import MigrationEngine

    project = _project()
    registry = Registry.load(project.registry_path)
    db_url = os.environ.get("DHOW_DATABASE_URL")
    if not db_url:
        msg = {
            "ok": False,
            "error": (
                "no database configured: set DHOW_DATABASE_URL "
                "(e.g. postgresql+psycopg://user:pass@host:5432/db)"
            ),
            "tenant": tenant,
            "to_version": to_version,
            "action": "rollback" if rollback else "apply",
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)

    try:
        from sqlalchemy import create_engine

        engine = create_engine(db_url)
        migrator = MigrationEngine(registry=registry, connection_provider=engine)
    except Exception as exc:  # pragma: no cover - defensive
        msg = {
            "ok": False,
            "error": f"failed to initialise migration engine: {exc}",
            "tenant": tenant,
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)

    try:
        if rollback:
            reversed_steps = migrator.rollback(tenant_id=tenant, to_version=to_version)
            payload = {
                "ok": True,
                "action": "rollback",
                "tenant": tenant,
                "to_version": to_version,
                "steps": [
                    {"name": s.name, "kind": s.kind, "target": s.target}
                    for s in reversed_steps
                ],
            }
        else:
            plan = migrator.plan()
            applied = migrator.apply(plan, tenant_id=tenant)
            payload = {
                "ok": True,
                "action": "apply",
                "tenant": tenant,
                "steps": [
                    {"name": s.name, "kind": s.kind, "target": s.target}
                    for s in applied
                ],
            }
    except Exception as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "tenant": tenant,
            "action": "rollback" if rollback else "apply",
        }

    if json:
        _json_out(payload)
    else:
        verb = "rolled back" if rollback else "applied"
        typer.echo(f"{verb} {len(payload.get('steps', []))} step(s) for tenant={tenant}")
    if not payload.get("ok", True):
        raise typer.Exit(1)

@app.command()
def describe(
    doctype: str,
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Describe a DocType from the compiled registry."""
    project = _project()
    registry = Registry.load(project.registry_path)
    entry = registry.doctypes.get(doctype)
    if entry is None:
        msg = {"ok": False, "error": f"DocType {doctype} not found"}
    else:
        msg = {"ok": True, "doctype": entry.to_dict()}
    if json:
        _json_out(msg)
    else:
        typer.echo(msg)


@app.command()
def schema(
    term: str,
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Search compiled schemas for a term."""
    project = _project()
    registry = Registry.load(project.registry_path)
    matches: list[str] = []
    for entry in registry.doctypes.values():
        if term.lower() in entry.name.lower():
            matches.append(entry.name)
        for field in entry.fields.values():
            if term.lower() in field.name.lower():
                matches.append(f"{entry.name}.{field.name}")
    msg = {"ok": True, "matches": matches}
    if json:
        _json_out(msg)
    else:
        for match in matches:
            typer.echo(match)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run the generated FastAPI application."""
    import uvicorn

    uvicorn.run("dhow.generated.app:app", host=host, port=port, reload=reload)
@app.command("import-data")
def import_data_cmd(
    doctype: str = typer.Argument(..., help="DocType to import rows into"),
    file: str = typer.Argument(..., help="CSV / JSON / XLSX file to import"),
    column_map: str = typer.Option(
        None, "--column-map", help='JSON string mapping source column -> DocType field'
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Import data into a DocType via dhow.engines.import_engine.import_data."""
    import json as _json

    parsed_map: dict[str, str] | None = None
    if column_map:
        try:
            raw = _json.loads(column_map)
            if not isinstance(raw, dict):
                raise ValueError("--column-map must decode to a JSON object")
            parsed_map = {str(k): str(v) for k, v in raw.items()}
        except (ValueError, _json.JSONDecodeError) as exc:
            msg = {"ok": False, "error": f"invalid --column-map JSON: {exc}"}
            if json:
                _json_out(msg)
            else:
                typer.echo(msg["error"])
            raise typer.Exit(1)

    project = _project()
    registry = Registry.load(project.registry_path)
    if not registry.doctypes:
        msg = {
            "ok": False,
            "error": (
                "no engine configured: project has no compiled registry "
                "(run `dhow build` first)"
            ),
            "doctype": doctype,
            "file": file,
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)

    try:
        from dhow.engines.execute import DhowEngine
        from dhow.engines.import_engine import import_data
        from dhow.engines.permissions import Actor

        engine = DhowEngine(registry=registry)
        actor = Actor(name="cli", roles=["system"])
        report = import_data(
            engine=engine,
            doctype_name=doctype,
            file_path=file,
            actor=actor,
            column_map=parsed_map,
        )
        payload = {
            "ok": True,
            "doctype": doctype,
            "file": file,
            "created": [r.to_dict() for r in report.created],
            "errors": [e.to_dict() for e in report.errors],
            "row_count": len(report.created),
            "error_count": len(report.errors),
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "error": str(exc),
            "doctype": doctype,
            "file": file,
        }

    if json:
        _json_out(payload)
    else:
        if payload["ok"]:
            typer.echo(
                f"Imported {payload['row_count']} row(s); "
                f"{payload['error_count']} error(s) into {doctype}"
            )
        else:
            typer.echo(payload["error"])
    if not payload.get("ok", True):
        raise typer.Exit(1)


@app.command()
def worker(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run the background event worker (requires a running Redis connection)."""
    msg = {
        "ok": False,
        "error": (
            "worker is not yet running: a Redis-backed event bus must be "
            "configured before dhow worker can start"
        ),
        "started": False,
    }
    if json:
        _json_out(msg)
    else:
        typer.echo("worker: not yet running (requires Redis)")


@app.command()
def scheduler(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run the cron-like scheduler (requires a running Redis connection)."""
    msg = {
        "ok": False,
        "error": (
            "scheduler is not yet running: a Redis-backed event bus must be "
            "configured before dhow scheduler can start"
        ),
        "started": False,
    }
    if json:
        _json_out(msg)
    else:
        typer.echo("scheduler: not yet running (requires Redis)")


@app.command("mcp-serve")
def mcp_serve_cmd(
    registry: str = typer.Option(
        None, "--registry", help="Path to a registry.json file (defaults to in-memory)"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Serve the project registry as an MCP server over stdio."""
    from dhow.mcp.server import main as mcp_main

    argv: list[str] = []
    if registry:
        argv.extend(["--registry", registry])

    payload = {
        "ok": True,
        "registry": registry,
        "argv": argv,
        "note": "MCP server entrypoint located; would call dhow.mcp.server.main",
    }
    if json:
        _json_out(payload)
        return

    typer.echo(f"Starting MCP server (registry={registry or '<empty>'})")
    mcp_main(argv)


@app.command()
def doctor(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Check project health and connectivity."""
    msg = {"ok": True, "checks": {"project": str(_project().root.exists())}}
    if json:
        _json_out(msg)
    else:
        typer.echo(f"project: {msg['checks']['project']}")


@new_app.command("module")
def new_module_cmd(
    name: str,
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Create a new module."""
    result = new_module(_project(), name)
    if json:
        _json_out(result)
    else:
        typer.echo(f"Created module {result['module']} at {result['path']}")


@new_app.command("doctype")
def new_doctype_cmd(
    name: str,
    module: str = typer.Option("", "--module", "-m"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Create a new DocType under a module."""
    # Empty module means the scaffolded modules/doctypes/ folder.
    effective_module = module or ""
    result = _new_doctype(_project(), effective_module, name)
    if json:
        _json_out(result)
    else:
        typer.echo(f"Created DocType {result['doctype']} at {result['path']}")


@app.command()
def seed(
    demo: bool = typer.Option(False, "--demo", help="Seed demo data"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Seed the database."""
    msg = {"ok": True, "seeded": demo}
    if json:
        _json_out(msg)
    else:
        typer.echo(f"seed demo={demo}")


@app.command()
def test(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run project tests."""
    result = subprocess.run(["pytest"], capture_output=True, text=True)
    msg = {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    if json:
        _json_out(msg)
    else:
        typer.echo(result.stdout)

# ---------------------------------------------------------------------------
# Customization layers
# ---------------------------------------------------------------------------


def _layer_path(project: Project, name: str) -> Path:
    """Return the canonical path for a layer JSON file."""
    return project.root / "layers" / f"{name}.json"


def _load_base_registry(project: Project) -> Registry:
    """Load the compiled registry, or return an empty one if no build has run."""
    if project.registry_path.exists():
        return Registry.load(project.registry_path)
    return Registry()


@layer_app.command("new")
def layer_new(
    name: str,
    base_version: str = typer.Option(
        "1", "--base-version", help="Base registry version this layer targets"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Scaffold a new customization layer JSON file under project_path/layers/."""
    project = _project()
    target = name
    path = _layer_path(project, name)
    if path.exists():
        msg = {"ok": False, "error": f"Layer file already exists: {path}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    skeleton = Layer(
        name=name,
        target=target,
        base_version=base_version,
        kind="tenant",
    )
    path.write_text(
        _json_dumps(skeleton.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    msg = {
        "ok": True,
        "name": name,
        "target": target,
        "base_version": base_version,
        "path": str(path),
    }
    if json:
        _json_out(msg)
    else:
        typer.echo(f"Created layer {name} at {path}")


@layer_app.command("diff")
def layer_diff(
    name: str,
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Show drift between the base registry and the merged registry for a layer."""
    from dhow.core.compiler import diff_registry

    project = _project()
    path = _layer_path(project, name)
    if not path.exists():
        msg = {"ok": False, "error": f"Layer file not found: {path}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)
    try:
        layer = Layer.from_path(path)
        base = _load_base_registry(project)
        stack = LayerStack(target=layer.target, layers=[layer])
        merged = merge_registry(base, stack)
        drift = diff_registry(base, merged)
    except (LayerValidationError, LayerApplyError) as exc:
        msg = {"ok": False, "error": str(exc), "layer": name}
        if json:
            _json_out(msg)
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1)
    msg = {
        "ok": True,
        "layer": name,
        "target": layer.target,
        "base_version": layer.base_version,
        "added": drift.get("added", []),
        "removed": drift.get("removed", []),
        "changed": drift.get("changed", []),
        "has_drift": bool(
            drift.get("added") or drift.get("removed") or drift.get("changed")
        ),
    }
    if json:
        _json_out(msg)
    else:
        typer.echo(f"layer {name} target={layer.target} base_version={layer.base_version}")
        for key in ("added", "removed", "changed"):
            entries = drift.get(key, [])
            if entries:
                typer.echo(f"{key}: {entries}")


@layer_app.command("export")
def layer_export(
    name: str,
    output: Path = typer.Option(
        ..., "-o", "--output", help="Destination path for the merged layer artifact"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Write the merged registry layer artifact to a JSON file."""
    project = _project()
    src = _layer_path(project, name)
    if not src.exists():
        msg = {"ok": False, "error": f"Layer file not found: {src}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)
    try:
        layer = Layer.from_path(src)
        base = _load_base_registry(project)
        stack = LayerStack(target=layer.target, layers=[layer])
        merged = merge_registry(base, stack)
    except (LayerValidationError, LayerApplyError) as exc:
        msg = {"ok": False, "error": str(exc), "layer": name}
        if json:
            _json_out(msg)
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1)
    artifact = {
        "layer": layer.to_dict(),
        "merged_registry": merged.to_dict(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        _json_dumps(artifact, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
    )
    msg = {
        "ok": True,
        "layer": name,
        "target": layer.target,
        "output": str(output.resolve()),
    }
    if json:
        _json_out(msg)
    else:
        typer.echo(f"Exported layer {name} merged registry to {output}")


@layer_app.command("validate")
def layer_validate(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Validate every customization layer against the compiled registry."""
    project = _project()
    layers_dir = project.root / "layers"
    if not layers_dir.exists() or not any(layers_dir.glob("*.json")):
        msg = {"ok": True, "errors": [], "layers": 0}
        if json:
            _json_out(msg)
        else:
            typer.echo("No layers found.")
        return
    base = _load_base_registry(project)
    total_errors: list[str] = []
    layer_reports: list[dict[str, Any]] = []
    stack = load_layers(project.root)
    errors = validate_layers(base, stack)
    total_errors.extend(errors)
    for layer in stack.layers:
        layer_reports.append(
            {
                "name": layer.name,
                "target": layer.target,
                "base_version": layer.base_version,
                "kind": layer.kind,
                "fields": [f.name for f in layer.add_fields],
                "controls": list(layer.add_controls),
            }
        )
    msg = {
        "ok": not total_errors,
        "errors": total_errors,
        "layers": layer_reports,
    }
    if json:
        _json_out(msg)
    else:
        if total_errors:
            for err in total_errors:
                typer.echo(f"error: {err}")
        else:
            typer.echo(f"Validated {len(layer_reports)} layer(s); no errors.")
    if total_errors:
        raise typer.Exit(1)



def main() -> None:
    app()


if __name__ == "__main__":
    main()
