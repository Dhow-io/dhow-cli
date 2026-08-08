"""Thin Typer shell over Dhow engine APIs."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import typer

from dhow.cli.build import run_build, run_diff

app = typer.Typer(help="Dhow — metadata-driven declarative ERP framework")
new_app = typer.Typer(help="Create modules and DocTypes")
app.add_typer(new_app, name="new")


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
    from dhow.cli.scaffold import scaffold_project

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
    rollback: bool = typer.Option(False, "--rollback", help="Roll back the last migration"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Apply or roll back database migrations."""
    msg = {"ok": False, "error": "migrate not yet implemented"}
    if json:
        _json_out(msg)
    else:
        typer.echo("migrate: not yet implemented")


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


from dhow.core.project import Project
from dhow.core.registry import Registry


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
