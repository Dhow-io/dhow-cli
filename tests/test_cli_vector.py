"""CLI tests for the ``dhow vector search`` command.

Tests cover three paths:

1. Pure-SQL preview when no live database is configured.
2. JSON output and the error path when the DocType is missing.
3. Live-DB execution path — skipped unless ``DHOW_DATABASE_URL`` is set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dhow_cli.main import app

runner = CliRunner()


def _scaffold_vector_project(root: Path, name: str) -> Path:
    """Scaffold a Dhow project with one vector DocType registered as ``Document``."""
    from dhow_cli.scaffold import scaffold_project

    project_path = scaffold_project(name, root / name)
    doctypes_dir = project_path / "modules" / "doctypes"
    doctypes_dir.mkdir(parents=True, exist_ok=True)
    (doctypes_dir / "__init__.py").touch(exist_ok=True)
    (doctypes_dir / "document.py").write_text(
        "from dhow import DocType, field\n\n"
        "class Document(DocType):\n"
        "    title = field.Text(required=True)\n"
        "    embedding = field.Vector(dim=4, metric='cosine')\n",
        encoding="utf-8",
    )
    return project_path


def test_vector_search_help_lists_arguments():
    """The ``dhow vector search --help`` output mentions doctype, field, --vector, --json."""
    result = runner.invoke(app, ["vector", "search", "--help"])
    assert result.exit_code == 0
    assert "doctype" in result.output
    assert "field" in result.output
    assert "--vector" in result.output
    assert "--json" in result.output
    assert "similarity" in result.output.lower()


def test_vector_search_unknown_doctype_returns_json_error(tmp_path, monkeypatch):
    """When the DocType is missing the command emits JSON error and exits 1."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "vector",
            "search",
            "Missing",
            "embedding",
            "--vector",
            "[0.1,0.2,0.3,0.4]",
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert '"ok": false' in result.output
    assert "Missing" in result.output


def test_vector_search_emits_sql_when_no_db(tmp_path, monkeypatch):
    """With no ``DHOW_DATABASE_URL`` and a project containing the DocType, the
    command emits the generated SQL without touching a database.
    """
    project_path = _scaffold_vector_project(tmp_path, "vecproj")
    monkeypatch.chdir(project_path)
    monkeypatch.delenv("DHOW_DATABASE_URL", raising=False)
    build_result = runner.invoke(app, ["build"])
    assert build_result.exit_code == 0, build_result.output

    result = runner.invoke(
        app,
        [
            "vector",
            "search",
            "Document",
            "embedding",
            "--vector",
            "[0.1,0.2,0.3,0.4]",
            "--limit",
            "3",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"ok": true' in result.output
    assert '"executed": false' in result.output
    assert "dt_document" in result.output
    assert "embedding <=>" in result.output  # cosine operator in SQL


def test_vector_search_supports_metric_override(tmp_path, monkeypatch):
    """``--metric`` override is reflected in the generated SQL."""
    project_path = _scaffold_vector_project(tmp_path, "vecproj2")
    monkeypatch.chdir(project_path)
    monkeypatch.delenv("DHOW_DATABASE_URL", raising=False)
    assert runner.invoke(app, ["build"]).exit_code == 0

    result = runner.invoke(
        app,
        [
            "vector",
            "search",
            "Document",
            "embedding",
            "--vector",
            "[0.1,0.2,0.3,0.4]",
            "--metric",
            "l2",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "embedding <->" in result.output


def test_vector_search_non_json_output_dumps_sql(tmp_path, monkeypatch):
    """Without --json the command prints the SQL on stdout."""
    project_path = _scaffold_vector_project(tmp_path, "vecproj3")
    monkeypatch.chdir(project_path)
    monkeypatch.delenv("DHOW_DATABASE_URL", raising=False)
    assert runner.invoke(app, ["build"]).exit_code == 0

    result = runner.invoke(
        app,
        [
            "vector",
            "search",
            "Document",
            "embedding",
            "--vector",
            "[0.1,0.2,0.3,0.4]",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "SELECT id, embedding" in result.output


def test_vector_search_dim_mismatch_error(tmp_path, monkeypatch):
    """A query vector whose length disagrees with ``dim`` produces a JSON error."""
    project_path = _scaffold_vector_project(tmp_path, "vecproj4")
    monkeypatch.chdir(project_path)
    monkeypatch.delenv("DHOW_DATABASE_URL", raising=False)
    assert runner.invoke(app, ["build"]).exit_code == 0

    result = runner.invoke(
        app,
        [
            "vector",
            "search",
            "Document",
            "embedding",
            "--vector",
            "[0.1,0.2,0.3]",  # length 3, expected 4
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert '"ok": false' in result.output
    assert "dim=4" in result.output


LIVE_URL = os.environ.get("DHOW_DATABASE_URL")


@pytest.mark.skipif(not LIVE_URL, reason="DHOW_DATABASE_URL not configured")
def test_vector_search_live_db_returns_results(tmp_path, monkeypatch):
    """With a live database, the command executes and returns ranked rows."""
    import sqlalchemy

    from dhow.engines.persistence import pgvector_extension_ddl

    project_path = _scaffold_vector_project(tmp_path, "vecproj5")
    monkeypatch.chdir(project_path)
    monkeypatch.setenv("DHOW_DATABASE_URL", LIVE_URL)
    assert runner.invoke(app, ["build"]).exit_code == 0

    eng = sqlalchemy.create_engine(LIVE_URL)
    try:
        with eng.begin() as conn:
            conn.execute(sqlalchemy.text(pgvector_extension_ddl()))
            conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS dt_document"))
            conn.execute(
                sqlalchemy.text(
                    "CREATE TABLE dt_document ("
                    "id uuid PRIMARY KEY, tenant_id uuid, "
                    "created_at timestamptz, updated_at timestamptz, "
                    "created_by text, updated_by text, "
                    "title text, embedding vector(4))"
                )
            )
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO dt_document (id, tenant_id, created_at, updated_at, title, embedding) "
                    "VALUES "
                    "('11111111-1111-1111-1111-111111111111', "
                    "'22222222-2222-2222-2222-222222222222', now(), now(), 'near', '[1.0,1.0,1.0,1.0]'),"
                    "('33333333-3333-3333-3333-333333333333', "
                    "'22222222-2222-2222-2222-222222222222', now(), now(), 'far', '[-1.0,-1.0,-1.0,-1.0]')"
                )
            )
        result = runner.invoke(
            app,
            [
                "vector",
                "search",
                "Document",
                "embedding",
                "--vector",
                "[1.0,1.0,1.0,1.0]",
                "--limit",
                "1",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        assert '"executed": true' in result.output
        assert '"count": 1' in result.output
        assert '"near"' in result.output
    finally:
        with eng.begin() as conn:
            conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS dt_document"))
        eng.dispose()