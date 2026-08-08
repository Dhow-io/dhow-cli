"""Tests for `dhow migrate`, `dhow import-data`, `dhow worker`, and `dhow mcp-serve`.

These commands are intentionally stub-safe: they must always succeed at the
CLI surface and emit structured JSON, even when the underlying engine is not
configured (no database, no compiled registry, no Redis, no MCP registry).
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dhow_cli.main import app
from dhow_cli.scaffold import scaffold_project

runner = CliRunner()


def _scaffold_and_chdir(tmp_path: Path) -> Path:
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    return project_path


def test_migrate_json_no_database(tmp_path: Path):
    """`dhow migrate --json` without DHOW_DATABASE_URL reports a clean error."""
    _scaffold_and_chdir(tmp_path)
    # Make sure no DB URL leaks in from the host environment.
    import os

    os.environ.pop("DHOW_DATABASE_URL", None)

    result = runner.invoke(app, ["migrate", "--json"])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "no database configured" in payload["error"]
    assert payload["action"] == "apply"


def test_migrate_rollback_json_no_database(tmp_path: Path):
    """`dhow migrate --rollback --to-version 1 --json` stub-safe JSON."""
    _scaffold_and_chdir(tmp_path)
    import os

    os.environ.pop("DHOW_DATABASE_URL", None)

    result = runner.invoke(
        app, ["migrate", "--rollback", "--to-version", "1", "--json"]
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "no database configured" in payload["error"]
    assert payload["action"] == "rollback"
    assert payload["to_version"] == "1"


def test_migrate_help_renders(tmp_path: Path):
    """`dhow migrate --help` works."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["migrate", "--help"])
    assert result.exit_code == 0
    assert "Migrate" in result.output or "migrate" in result.output.lower()
    assert "--tenant" in result.output
    assert "--rollback" in result.output
    assert "--to-version" in result.output


def test_migrate_tenant_option_json(tmp_path: Path):
    """`dhow migrate --tenant acme --json` surfaces the tenant in the stub payload."""
    _scaffold_and_chdir(tmp_path)
    import os

    os.environ.pop("DHOW_DATABASE_URL", None)

    result = runner.invoke(app, ["migrate", "--tenant", "acme", "--json"])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["tenant"] == "acme"


def test_import_data_json_no_registry(tmp_path: Path):
    """`dhow import-data --json` reports a friendly message when no registry."""
    project_path = _scaffold_and_chdir(tmp_path)
    # Don't run `dhow build`, so no compiled registry exists.
    csv_path = project_path / "rows.csv"
    csv_path.write_text("title\nhello\n", encoding="utf-8")

    result = runner.invoke(
        app, ["import-data", "Invoice", str(csv_path), "--json"]
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "no engine configured" in payload["error"]
    assert payload["doctype"] == "Invoice"
    assert payload["file"] == str(csv_path)


def test_import_data_invalid_column_map(tmp_path: Path):
    """`dhow import-data --column-map 'not json' --json` reports invalid JSON."""
    project_path = _scaffold_and_chdir(tmp_path)
    csv_path = project_path / "rows.csv"
    csv_path.write_text("title\nhello\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["import-data", "Invoice", str(csv_path), "--column-map", "not json", "--json"],
    )
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "invalid --column-map JSON" in payload["error"]


def test_import_data_help_renders(tmp_path: Path):
    """`dhow import-data --help` works."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["import-data", "--help"])
    assert result.exit_code == 0
    assert "--column-map" in result.output
    assert "--json" in result.output


def test_worker_json(tmp_path: Path):
    """`dhow worker --json` returns structured not-yet-running output."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["worker", "--json"])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["started"] is False
    assert "Redis" in payload["error"]


def test_worker_help_renders(tmp_path: Path):
    """`dhow worker --help` works."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["worker", "--help"])
    assert result.exit_code == 0
    assert "worker" in result.output.lower()


def test_scheduler_json(tmp_path: Path):
    """`dhow scheduler --json` returns structured not-yet-running output."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["scheduler", "--json"])
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["started"] is False
    assert "Redis" in payload["error"]


def test_scheduler_help_renders(tmp_path: Path):
    """`dhow scheduler --help` works."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["scheduler", "--help"])
    assert result.exit_code == 0
    assert "scheduler" in result.output.lower()


def test_mcp_serve_help(tmp_path: Path):
    """`dhow mcp-serve --help` works."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["mcp-serve", "--help"])
    assert result.exit_code == 0
    assert "--registry" in result.output


def test_mcp_serve_json_no_registry(tmp_path: Path):
    """`dhow mcp-serve --json` without --registry returns structured output."""
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["mcp-serve", "--json"])
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["registry"] is None
    assert payload["argv"] == []


def test_mcp_serve_json_with_registry(tmp_path: Path):
    """`dhow mcp-serve --json --registry <path>` surfaces the registry in the payload."""
    project_path = _scaffold_and_chdir(tmp_path)
    # Build the project so we have a real registry path.
    build = runner.invoke(app, ["build"])
    assert build.exit_code == 0, build.output
    registry_path = project_path / "migrations" / "dhow_registry.json"
    assert registry_path.exists()

    result = runner.invoke(
        app, ["mcp-serve", "--registry", str(registry_path), "--json"]
    )
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["registry"] == str(registry_path)
    assert payload["argv"] == ["--registry", str(registry_path)]
