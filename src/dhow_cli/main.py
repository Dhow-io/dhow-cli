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
from dhow_cli.generate import run_generate_ui
from dhow_cli.app_commands import load_app_commands, run_hook
from dhow_cli.new import new_module
from dhow_cli.workspace import discover_workspace, write_apps_list
from dhow.core.layers import (
    Layer,
    LayerApplyError,
    LayerStack,
    LayerValidationError,
    load_layers,
    merge_registry,
    validate_layers,
)
from dhow.skills import SkillLoadError, load_skills
# Local alias to avoid shadowing by per-command `json: bool` Typer options.
from json import dumps as _json_dumps


app = typer.Typer(help="Dhow — metadata-driven declarative ERP framework")
new_app = typer.Typer(help="Create modules and DocTypes")
app.add_typer(new_app, name="new")
layer_app = typer.Typer(help="Manage customization layers (JSON patches on top of the registry)")
app.add_typer(layer_app, name="layer")
vector_app = typer.Typer(help="Vector similarity search (pgvector)")
app.add_typer(vector_app, name="vector")
skill_app = typer.Typer(help="Inspect and render the project's Agent Skill library")
app.add_typer(skill_app, name="skill")
query_app = typer.Typer(help="Semantic queries + sandboxed text-to-SQL fallback")
app.add_typer(query_app, name="query")
attachments_app = typer.Typer(help="Inspect and download attachments from the metadata index")
app.add_typer(attachments_app, name="attachments")


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


def _workspace() -> Workspace | None:
    return discover_workspace()


def _require_workspace() -> Workspace:
    ws = discover_workspace()
    if ws is None:
        typer.echo("Not inside a Dhow workspace (missing apps/ and sites/ directories).")
        raise typer.Exit(1)
    return ws


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


@app.command("init-workspace")
def init_workspace(
    name: str,
    path: str = typer.Option(".", help="Directory in which to create the workspace"),
    framework_url: str = typer.Option(
        "https://github.com/Dhow-io/dhow.git",
        "--framework-url",
        help="Git URL for the Dhow framework",
    ),
    cli_url: str = typer.Option(
        "https://github.com/Dhow-io/dhow-cli.git",
        "--cli-url",
        help="Git URL for the Dhow CLI",
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Create a Dhow workspace with apps/ and sites/ directories."""
    from dhow_cli.workspace import Workspace, write_apps_list

    root = Path(path).resolve() / name
    apps = root / "apps"
    sites = root / "sites"
    apps.mkdir(parents=True, exist_ok=True)
    sites.mkdir(parents=True, exist_ok=True)

    ws = Workspace(
        root=root,
        apps_path=apps,
        sites_path=sites,
        config_path=root / "dhow.toml",
        apps=["dhow"],
        app_contracts={},
    )
    write_apps_list(ws, ["dhow"])

    (root / "dhow.toml").write_text(
        '[workspace]\nname = "' + name + '"\n\n[apps]\nrequired = ["dhow"]\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"# {name}\n\nDhow workspace.\n\n"
        "```bash\n"
        f"cd {name}/apps\n"
        f"git clone {framework_url}\n"
        f"git clone {cli_url}\n"
        "cd ..\n"
        "dhow migrate\n"
        "```\n",
        encoding="utf-8",
    )

    result = {
        "ok": True,
        "path": str(root),
        "name": name,
        "apps": ["dhow"],
        "framework_url": framework_url,
        "cli_url": cli_url,
    }
    if json:
        _json_out(result)
    else:
        typer.echo(f"Created Dhow workspace '{name}' at {root}")
        typer.echo(f"  apps: {apps}")
        typer.echo(f"  sites: {sites}")


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


@vector_app.command("search")
def vector_search_cmd(
    doctype: str = typer.Argument(..., help="DocType that owns the vector field"),
    field: str = typer.Argument(..., help="Name of the field.Vector column"),
    vector: str = typer.Option(
        ..., "--vector", help="Query embedding as JSON (e.g. '[0.1,0.2,0.3]')"
    ),
    limit: int = typer.Option(10, "--limit", help="Maximum rows to return"),
    metric: str = typer.Option(
        None,
        "--metric",
        help="Override distance metric (cosine|l2|ip). Default uses the field declaration.",
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run a pgvector similarity search against a DocType's vector column.

    With ``DHOW_DATABASE_URL`` set the command runs against the live
    database; without it the command emits the parameterized SQL the
    runner would execute so it is useful for testing and review.
    """
    project = _project()
    registry = Registry.load(project.registry_path) if project.registry_path.exists() else Registry()

    from dhow.engines.vector import (
        similarity_search,
        similarity_search_sql,
    )

    db_url = os.environ.get("DHOW_DATABASE_URL")

    try:
        sql, params = similarity_search_sql(
            registry,
            doctype=doctype,
            field=field,
            query_vector=vector,
            limit=limit,
            metric=metric,
        )
    except (KeyError, ValueError) as exc:
        msg = {"ok": False, "error": str(exc), "doctype": doctype, "field": field}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)

    if not db_url:
        msg = {
            "ok": True,
            "executed": False,
            "note": "DHOW_DATABASE_URL is unset; emitting generated SQL only",
            "doctype": doctype,
            "field": field,
            "metric": metric,
            "limit": limit,
            "sql": sql,
            "params": {k: str(v) for k, v in params.items()},
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(sql)
            typer.echo(f"-- params: {params}")
        return

    try:
        from sqlalchemy import create_engine

        engine = create_engine(db_url)
        results = similarity_search(
            engine,
            registry,
            doctype=doctype,
            field=field,
            query_vector=vector,
            limit=limit,
            metric=metric,
        )
        msg = {
            "ok": True,
            "executed": True,
            "doctype": doctype,
            "field": field,
            "metric": metric,
            "limit": limit,
            "results": [
                {"id": r.id, "distance": r.distance, "row": r.row} for r in results
            ],
            "count": len(results),
        }
    except Exception as exc:  # pragma: no cover - DB path is best-effort
        msg = {
            "ok": False,
            "error": str(exc),
            "doctype": doctype,
            "field": field,
            "sql": sql,
        }

    if json:
        _json_out(msg)
    else:
        if msg.get("executed"):
            typer.echo(
                f"{msg.get('count', 0)} match(es) for {doctype}.{field}"
                + (f" (metric={msg.get('metric')})" if msg.get("metric") else "")
            )
            for r in msg.get("results", []):
                typer.echo(f"{r['id']}\t{r['distance']}")
        else:
            typer.echo(msg.get("error", "vector search failed"))
    if not msg.get("ok", True):
        raise typer.Exit(1)


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


@app.command("test-upgrade")
def test_upgrade_cmd(
    corpus: str = typer.Option(
        ...,
        "--corpus",
        help="Path to an upgrade-safety corpus JSON file (see dhow.engines.upgrade).",
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run the upgrade-safety corpus against the migration planner.

    Loads the JSON corpus (see ``dhow.engines.upgrade``) and asserts that
    every scenario produces the expected migration plan. Exits non-zero
    on the first drift; returns a JSON summary with ``--json``.
    """
    from dhow.engines.upgrade import assert_upgrade_safe, summarize

    try:
        results = assert_upgrade_safe(corpus)
    except FileNotFoundError as exc:
        msg = {"ok": False, "error": str(exc), "corpus": corpus}
        if json:
            _json_out(msg)
        else:
            typer.echo(f"upgrade corpus not found: {corpus}", err=True)
        raise typer.Exit(1)
    except ValueError as exc:
        msg = {"ok": False, "error": str(exc), "corpus": corpus}
        if json:
            _json_out(msg)
        else:
            typer.echo(f"upgrade corpus is invalid: {exc}", err=True)
        raise typer.Exit(1)
    except AssertionError as exc:
        msg = {"ok": False, "error": str(exc), "corpus": corpus}
        if json:
            _json_out(msg)
        else:
            typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    summary = summarize(results)
    summary["ok"] = summary["unsafe"] == 0
    summary["corpus"] = corpus
    if json:
        _json_out(summary)
    else:
        typer.echo(
            f"upgrade corpus {corpus}: {summary['safe']}/{summary['total']} safe"
        )
    if not summary["ok"]:
        raise typer.Exit(1)

@app.command("generate-ui")
def generate_ui_cmd(
    output: str = typer.Option(
        None, "--output", "-o", help="Output directory for the generated React UI"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Generate a React/TypeScript Desk UI from the compiled registry."""
    project = _project()
    try:
        result = run_generate_ui(project, output=Path(output) if output else None)
    except Exception as exc:
        msg = {"ok": False, "error": str(exc)}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)
    if json:
        _json_out(result)
    else:
        typer.echo(f"Generated UI at {result['output']}")
        typer.echo(f"Files: {len(result['files'])}")
    if not result.get("ok", True):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


def _attachments_root(project: Project) -> Path:
    """Return the local attachment storage root for a project.

    The path is read from ``[attachments] local_root`` in ``dhow.toml`` when
    present; otherwise it defaults to ``<project>/.dhow-attachments``.
    """
    config = getattr(project, "config", {}) or {}
    attachments_cfg = config.get("attachments", {}) or {}
    raw = attachments_cfg.get("local_root")
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = project.root / path
        return path.resolve()
    return (project.root / ".dhow-attachments").resolve()


def _attachments_db_url(project: Project) -> str | None:
    """Return the database URL used to record attachment metadata.

    Falls back to the ``DHOW_DATABASE_URL`` environment variable when no
    project-scoped URL is configured. Returns ``None`` when neither is set,
    which the ``attach`` command turns into a clear error.
    """
    config = getattr(project, "config", {}) or {}
    project_cfg = config.get("project", {}) or {}
    url = project_cfg.get("database_url") or project_cfg.get("attachments_database_url")
    return url or os.environ.get("DHOW_DATABASE_URL")


@app.command("attach")
def attach_cmd(
    file: Path = typer.Argument(..., help="Path to the file to attach"),
    doctype: str = typer.Option(..., "--doctype", "-d", help="Owning DocType"),
    doc_id: str = typer.Option(..., "--doc-id", "-i", help="Owning document id"),
    field_name: str = typer.Option(
        "attachment",
        "--field",
        "-f",
        help="Name of the attachment field on the DocType",
    ),
    key: str | None = typer.Option(
        None,
        "--key",
        "-k",
        help="Storage key (defaults to '<doctype>/<doc-id>/<filename>')",
    ),
    content_type: str | None = typer.Option(
        None, "--content-type", help="Override the guessed content type"
    ),
    metadata: str | None = typer.Option(
        None,
        "--metadata",
        help="Inline JSON object of metadata to attach (e.g. '{\"source\": \"email\"}')",
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Upload a file to the project's attachment store.

    Thin wrapper over :class:`dhow.attachments.AttachmentStore`: validates
    inputs, resolves the configured backend, then records metadata in the
    ``dhow_attachment`` table.
    """
    import json as _json
    from dhow.attachments import AttachmentStore, LocalFileStorage

    project = _project()
    parsed_metadata: dict[str, Any] = {}
    if metadata:
        try:
            parsed = _json.loads(metadata)
        except _json.JSONDecodeError as exc:
            msg = {"ok": False, "error": f"invalid --metadata JSON: {exc}"}
            if json:
                _json_out(msg)
            else:
                typer.echo(msg["error"], err=True)
            raise typer.Exit(1)
        if not isinstance(parsed, dict):
            msg = {"ok": False, "error": "--metadata must be a JSON object"}
            if json:
                _json_out(msg)
            else:
                typer.echo(msg["error"], err=True)
            raise typer.Exit(1)
        parsed_metadata = parsed
    resolved_key = key or f"{doctype.lower()}/{doc_id}/{file.name}"

    if not file.exists():
        msg = {
            "ok": False,
            "error": f"file not found: {file}",
            "doctype": doctype,
            "doc_id": doc_id,
            "field": field_name,
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)
    if not file.is_file():
        msg = {
            "ok": False,
            "error": f"not a regular file: {file}",
            "doctype": doctype,
            "doc_id": doc_id,
            "field": field_name,
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    db_url = _attachments_db_url(project)
    if not db_url:
        msg = {
            "ok": False,
            "error": (
                "no database URL configured: set project.database_url in "
                "dhow.toml or DHOW_DATABASE_URL in the environment"
            ),
            "doctype": doctype,
            "doc_id": doc_id,
            "field": field_name,
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    backend = LocalFileStorage(_attachments_root(project))
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import Engine

        engine: Engine = create_engine(db_url, future=True)
    except Exception as exc:
        msg = {"ok": False, "error": f"failed to create SQLAlchemy engine: {exc}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    def _provider():
        return engine.connect()

    _provider._dhow_is_engine = True  # type: ignore[attr-defined]
    store = AttachmentStore(backend, _provider)

    try:
        store.ensure_schema()
        attachment = store.upload(
            file,
            key=resolved_key,
            doctype=doctype,
            doc_id=doc_id,
            field_name=field_name,
            content_type=content_type,
            metadata=parsed_metadata,
        )
    except Exception as exc:
        msg = {
            "ok": False,
            "error": str(exc),
            "doctype": doctype,
            "doc_id": doc_id,
            "field": field_name,
            "key": resolved_key,
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    msg = {
        "ok": True,
        "attachment": attachment.to_dict(),
        "doctype": doctype,
        "doc_id": doc_id,
        "field": field_name,
        "key": attachment.storage.key,
        "backend": attachment.storage.backend,
        "size_bytes": attachment.size_bytes,
        "checksum_sha256": attachment.checksum_sha256,
    }
    if json:
        _json_out(msg)
    else:
        typer.echo(
            f"Attached {attachment.filename} ({attachment.size_bytes} bytes) to "
            f"{doctype}/{doc_id}.{field_name} (key={attachment.storage.key})"
        )


@attachments_app.command("list")
def attachments_list_cmd(
    doctype: str = typer.Option(..., "--doctype", "-d", help="DocType to list for"),
    doc_id: str = typer.Option(..., "--doc-id", "-i", help="Document id to list for"),
    field_name: str | None = typer.Option(
        None, "--field", "-f", help="Optional: filter to a single attachment field"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """List every attachment recorded for a ``(doctype, doc_id)`` pair."""
    from dhow.attachments import AttachmentStore, LocalFileStorage

    project = _project()
    db_url = _attachments_db_url(project)
    if not db_url:
        msg = {
            "ok": False,
            "error": "no database URL configured for attachments",
        }
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    backend = LocalFileStorage(_attachments_root(project))
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import Engine

        engine: Engine = create_engine(db_url, future=True)
    except Exception as exc:
        msg = {"ok": False, "error": f"failed to create SQLAlchemy engine: {exc}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    def _provider():
        return engine.connect()

    _provider._dhow_is_engine = True  # type: ignore[attr-defined]
    store = AttachmentStore(backend, _provider)
    try:
        store.ensure_schema()
        rows = store.list(doctype, doc_id, field_name=field_name)
    except Exception as exc:
        msg = {"ok": False, "error": str(exc)}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    msg = {
        "ok": True,
        "doctype": doctype,
        "doc_id": doc_id,
        "count": len(rows),
        "attachments": [r.to_dict() for r in rows],
    }
    if field_name is not None:
        msg["field"] = field_name
    if json:
        _json_out(msg)
    else:
        if not rows:
            typer.echo(f"No attachments for {doctype}/{doc_id}.")
            return
        typer.echo(f"{len(rows)} attachment(s) for {doctype}/{doc_id}:")
        for row in rows:
            typer.echo(
                f"  - {row.id}  {row.filename}  ({row.size_bytes} B)  "
                f"key={row.storage.key}  field={row.field_name}"
            )


@attachments_app.command("download")
def attachments_download_cmd(
    attachment_id: str = typer.Argument(..., help="Attachment id returned by `dhow attach`"),
    output: Path = typer.Option(
..., "-o", "--output", help="Destination path for the downloaded bytes"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Download a single attachment to ``output``."""
    from dhow.attachments import AttachmentStore, LocalFileStorage

    project = _project()
    db_url = _attachments_db_url(project)
    if not db_url:
        msg = {"ok": False, "error": "no database URL configured for attachments"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    backend = LocalFileStorage(_attachments_root(project))
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.engine import Engine
        from sqlalchemy import text as _sql_text

        engine: Engine = create_engine(db_url, future=True)
    except Exception as exc:
        msg = {"ok": False, "error": f"failed to create SQLAlchemy engine: {exc}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)

    def _provider():
        return engine.connect()

    _provider._dhow_is_engine = True  # type: ignore[attr-defined]
    store = AttachmentStore(backend, _provider)
    try:
        store.ensure_schema()
        with engine.connect() as conn:
            row = conn.execute(
                _sql_text(
                    "SELECT id, doctype, doc_id, field_name, storage_backend, "
                    "storage_key, filename, content_type, size_bytes, "
                    "checksum_sha256, metadata, created_at, tenant_id "
                    "FROM dhow_attachment WHERE id = :id"
                ),
                {"id": attachment_id},
            ).mappings().first()
        if row is None:
            msg = {"ok": False, "error": f"attachment not found: {attachment_id}"}
            if json:
                _json_out(msg)
            else:
                typer.echo(msg["error"], err=True)
            raise typer.Exit(1)
        from dhow.attachments import Attachment

        attachment = Attachment.from_row(row)
        data = store.download_attachment(attachment)
    except typer.Exit:
        raise
    except Exception as exc:
        msg = {"ok": False, "error": str(exc)}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"], err=True)
        raise typer.Exit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    msg = {
        "ok": True,
        "id": attachment.id,
        "filename": attachment.filename,
        "path": str(output),
        "size_bytes": len(data),
    }
    if json:
        _json_out(msg)
    else:
        typer.echo(
            f"Downloaded {attachment.filename} ({len(data)} bytes) to {output}"
        )


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



# ---------------------------------------------------------------------------
# Agent Skills
# ---------------------------------------------------------------------------


def _skills_dir(project: Project) -> Path:
    """Return the canonical skills directory for a project."""
    return project.root / "skills"


def _load_project_skills(project: Project) -> dict[str, Any]:
    """Load every ``*.md`` under ``project.root/skills`` and return a payload.

    Returns the standard ``{"ok": ..., ...}`` envelope so every command can
    reuse it.
    """
    skills_dir = _skills_dir(project)
    if not skills_dir.exists() or not any(skills_dir.glob("*.md")):
        return {
            "ok": True,
            "skills": [],
            "count": 0,
            "directory": str(skills_dir),
            "errors": [],
        }
    try:
        registry = load_skills(skills_dir)
    except SkillLoadError as exc:
        return {
            "ok": False,
            "skills": [],
            "count": 0,
            "directory": str(skills_dir),
            "errors": [str(exc)],
        }
    return {
        "ok": True,
        "skills": registry.to_list(),
        "count": len(registry),
        "directory": str(skills_dir),
        "errors": [],
    }


@skill_app.command("list")
def skill_list(
    query: str | None = typer.Option(
        None, "--query", "-q", help="Optional search query to filter by keyword"
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Cap the number of returned matches"
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """List every skill under the project's ``skills/`` directory."""
    project = _project()
    payload = _load_project_skills(project)
    skills = payload["skills"]
    if query and payload["ok"]:
        from dhow.skills import load_skills as _load_skills

        try:
            registry = _load_skills(_skills_dir(project))
        except SkillLoadError as exc:
            payload["ok"] = False
            payload["errors"] = [str(exc)]
            skills = []
        else:
            skills = [s.to_dict() for s in registry.find(query, limit=limit)]
    elif limit is not None:
        skills = skills[:limit]
    payload["skills"] = skills
    payload["count"] = len(skills)
    if query is not None:
        payload["query"] = query
    if limit is not None:
        payload["limit"] = limit
    if json:
        _json_out(payload)
        if not payload["ok"]:
            raise typer.Exit(1)
        return
    if not payload["ok"]:
        for err in payload["errors"]:
            typer.echo(f"error: {err}")
        raise typer.Exit(1)
    if not skills:
        typer.echo(f"No skills found in {payload['directory']}.")
        return
    typer.echo(f"Skills ({len(skills)}) in {payload['directory']}:")
    for skill in skills:
        typer.echo(
            f"  - {skill['name']} (v{skill['version']}) — {skill['description'] or '(no description)'}"
        )


@skill_app.command("show")
def skill_show(
    name: str = typer.Argument(..., help="Name of the skill to render"),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Render the full markdown body of a single skill."""
    project = _project()
    skills_dir = _skills_dir(project)
    if not skills_dir.exists() or not any(skills_dir.glob("*.md")):
        msg = {"ok": False, "error": f"no skills directory: {skills_dir}"}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)
    try:
        registry = load_skills(skills_dir)
    except SkillLoadError as exc:
        msg = {"ok": False, "error": str(exc), "name": name}
        if json:
            _json_out(msg)
        else:
            typer.echo(f"error: {exc}")
        raise typer.Exit(1)
    if name not in registry:
        msg = {"ok": False, "error": f"unknown skill: {name!r}", "name": name}
        if json:
            _json_out(msg)
        else:
            typer.echo(msg["error"])
        raise typer.Exit(1)
    summary = registry.get(name).to_dict()
    body = registry.render(name)
    if json:
        _json_out({"ok": True, "skill": summary, "content": body})
        return
    typer.echo(f"# {summary['name']} (v{summary['version']})")
    if summary["description"]:
        typer.echo(summary["description"])
    if summary["triggers"]:
        typer.echo("")
        typer.echo("Triggers:")
        for trigger in summary["triggers"]:
            typer.echo(f"  - {trigger}")
    if summary["constraints"]:
        typer.echo("")
        typer.echo("Constraints:")
        for constraint in summary["constraints"]:
            typer.echo(f"  - {constraint}")
    typer.echo("")
    typer.echo(body)


# ---------------------------------------------------------------------------
# Semantic query + sandboxed text-to-SQL
# ---------------------------------------------------------------------------


def _query_table_registry(project: Project) -> "TableRegistry":
    """Build a :class:`TableRegistry` from the compiled registry's tables."""
    from dhow.query.sql import TableRegistry

    table_registry = TableRegistry()
    if project.registry_path.exists():
        registry = Registry.load(project.registry_path)
        for name in registry.doctypes:
            table_registry.add(f"dt_{name.lower()}")
    return table_registry


def _exit_with(msg: dict[str, Any], as_json: bool, code: int = 1) -> "typer.Exit":
    """Emit ``msg`` as JSON or human-readable text, then exit ``code``."""
    if as_json:
        _json_out(msg)
    else:
        typer.echo(msg.get("error", str(msg)))
    raise typer.Exit(code)


@query_app.command("run")
def query_run_cmd(
    metric: str = typer.Argument(..., help="Metric name (defined under project_path/metrics/)"),
    params: str = typer.Option(
        "",
        "--params",
        help="JSON object of metric parameters (e.g. '{\"filters\": {\"status\": \"draft\"}}')",
    ),
    actor: str = typer.Option(
        "system",
        "--actor",
        help="Actor role that executes the metric (defaults to 'system')",
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run a metric declared under project_path/metrics/ through the engine."""
    from dhow.engines.execute import DhowEngine
    from dhow.engines.permissions import Actor
    from dhow.query import load_metrics, query_metric as _query_metric
    # Per-function import to avoid shadowing by the ``json: bool`` Typer option.
    import json as _json
    from dhow.engines.execute import DhowEngine
    from dhow.engines.permissions import Actor
    from dhow.query import load_metrics, query_metric as _query_metric

    parsed_params: dict[str, Any] = {}
    if params:
        try:
            loaded = _json.loads(params)
        except _json.JSONDecodeError as exc:
            _exit_with(
                {"ok": False, "error": f"invalid --params JSON: {exc}", "metric": metric},
                json,
            )
        if not isinstance(loaded, dict):
            _exit_with(
                {
                    "ok": False,
                    "error": "--params must decode to a JSON object",
                    "metric": metric,
                },
                json,
            )
        parsed_params = loaded

    project = _project()
    registry = Registry.load(project.registry_path) if project.registry_path.exists() else Registry()
    metric_registry = load_metrics(project.root)
    if metric not in metric_registry.names():
        _exit_with(
            {
                "ok": False,
                "error": f"unknown metric: {metric!r}; known: {metric_registry.names()}",
                "metric": metric,
            },
            json,
        )

    engine = DhowEngine(registry=registry)
    roles = tuple(actor.split(",")) if actor else ("system",)
    exec_actor = Actor(roles=roles, agent_role=roles[0] if roles else None)

    result = _query_metric(
        engine,
        metric,
        parsed_params,
        registry=metric_registry,
        actor=exec_actor,
    )

    final = {"ok": result.ok, "result": result.to_dict()}
    if json:
        _json_out(final)
    else:
        typer.echo(_json_dumps(result.to_dict(), indent=2, default=str))
    if not result.ok:
        raise typer.Exit(1)


@query_app.command("list")
def query_list_cmd(
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """List every metric defined under project_path/metrics/."""
    from dhow.query import load_metrics

    project = _project()
    metric_registry = load_metrics(project.root)
    msg = {
        "ok": True,
        "count": len(metric_registry.metrics),
        "metrics": metric_registry.to_list(),
    }
    if json:
        _json_out(msg)
    else:
        if not metric_registry.metrics:
            typer.echo("No metrics found.")
            return
        for metric in metric_registry.to_list():
            typer.echo(
                f"{metric['name']}: doctype={metric['doctype']} "
                f"filters={metric['filters']} aggregations={metric['aggregations']}"
            )


@query_app.command("explain")
def query_explain_cmd(
    question: str = typer.Argument(..., help="Natural-language question to translate to SQL"),
    tables: str = typer.Option(
        None,
        "--tables",
        help="Comma-separated list of allowed tables (defaults to every doctype in the registry as dt_<name>)",
    ),
    json: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Translate a natural-language question to sandboxed SQL (read-only SELECT)."""
    from dhow.query import explain_sql

    project = _project()
    if tables:
        registry = [t.strip() for t in tables.split(",") if t.strip()]
    else:
        registry = _query_table_registry(project)
    plan = explain_sql(question, registry)
    msg = {"ok": not plan.violations, "plan": plan.to_dict()}
    if json:
        _json_out(msg)
    else:
        typer.echo(_json_dumps(plan.to_dict(), indent=2, default=str))
    if plan.violations:
        raise typer.Exit(1)


def _register_app_commands() -> None:
    """Discover installed Dhow apps and attach their CLI sub-apps."""
    workspace = discover_workspace()
    if workspace is None:
        return
    for app_name, group in load_app_commands(workspace).items():
        app.add_typer(group, name=app_name)


def main() -> None:
    _register_app_commands()
    app()

if __name__ == "__main__":
    main()
