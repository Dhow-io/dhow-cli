"""CLI tests for the `dhow query` subcommand (semantic + text-to-SQL)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dhow_cli.main import app
from dhow_cli.scaffold import scaffold_project


runner = CliRunner()


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create a Dhow project with metrics/ pre-populated."""
    project_path = scaffold_project("demo", tmp_path / "demo")
    cwd = os.getcwd()
    metrics_dir = project_path / "metrics"
    metrics_dir.mkdir(exist_ok=True)
    (metrics_dir / "invoice_count.yaml").write_text(
        "name: invoice_count\ndoctype: Invoice\ndescription: Total invoices\n",
        encoding="utf-8",
    )
    (metrics_dir / "submitted_total.yaml").write_text(
        (
            "name: submitted_total\n"
            "doctype: Invoice\n"
            "filters:\n  status: submitted\n"
            "aggregations:\n  - total_amount=sum(total)\n"
            "description: Sum of submitted invoice totals.\n"
        ),
        encoding="utf-8",
    )
    os.chdir(project_path)
    try:
        # Build so the registry has doctypes for the SQL explain path.
        result = runner.invoke(app, ["build"])
        assert result.exit_code == 0, result.output
        yield project_path
    finally:
        os.chdir(cwd)


# ---------------------------------------------------------------------------
# `dhow query list`
# ---------------------------------------------------------------------------


def test_query_list_json(project_path: Path):
    result = runner.invoke(app, ["query", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    names = sorted(m["name"] for m in payload["metrics"])
    assert names == ["invoice_count", "submitted_total"]
    submitted = next(m for m in payload["metrics"] if m["name"] == "submitted_total")
    assert submitted["doctype"] == "Invoice"
    assert submitted["filters"] == {"status": "submitted"}
    assert submitted["aggregations"] == ["total_amount=sum(total)"]


def test_query_list_human(project_path: Path):
    result = runner.invoke(app, ["query", "list"])
    assert result.exit_code == 0
    assert "invoice_count" in result.output
    assert "submitted_total" in result.output


def test_query_list_empty(tmp_path: Path):
    """When no metrics/ directory exists the command still exits cleanly."""
    project_path = scaffold_project("empty", tmp_path / "empty")
    cwd = os.getcwd()
    os.chdir(project_path)
    try:
        result = runner.invoke(app, ["query", "list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["metrics"] == []
        assert payload["count"] == 0
    finally:
        os.chdir(cwd)


# ---------------------------------------------------------------------------
# `dhow query run`
# ---------------------------------------------------------------------------


def test_query_run_json(project_path: Path):
    params = json.dumps({"filters": {"status": "submitted"}, "limit": 10})
    result = runner.invoke(
        app,
        ["query", "run", "submitted_total", "--params", params, "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    inner = payload["result"]
    assert inner["ok"] is True
    assert inner["metric"]["name"] == "submitted_total"
    assert inner["aggregations"] == {"total_amount": "sum(total)"}
    assert inner["expression"] is None
    assert inner["data"], "expected at least the persistence stub echo"


def test_query_run_default_limit(project_path: Path):
    result = runner.invoke(app, ["query", "run", "invoice_count", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True


def test_query_run_unknown_metric(project_path: Path):
    result = runner.invoke(app, ["query", "run", "does_not_exist", "--json"])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "unknown metric" in payload["error"]
    assert "submitted_total" in payload["error"]  # known metrics listed


def test_query_run_invalid_params_json(project_path: Path):
    result = runner.invoke(
        app,
        ["query", "run", "invoice_count", "--params", "{not json", "--json"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "invalid --params" in payload["error"]


def test_query_run_params_must_be_object(project_path: Path):
    result = runner.invoke(
        app,
        ["query", "run", "invoice_count", "--params", "[1, 2, 3]", "--json"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "JSON object" in payload["error"]


# ---------------------------------------------------------------------------
# `dhow query explain`
# ---------------------------------------------------------------------------


def test_query_explain_known_table(project_path: Path):
    result = runner.invoke(
        app,
        ["query", "explain", "How many invoices are there?", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    plan = payload["plan"]
    assert plan["sql"].startswith("SELECT COUNT(*) AS count FROM dt_invoice")
    assert plan["read_only"] is True
    assert plan["allowlisted"] is True
    assert plan["explainable"] is True
    assert plan["violations"] == []
    assert plan["metric"] == "count_rows"


def test_query_explain_with_tables_override(project_path: Path):
    result = runner.invoke(
        app,
        [
            "query",
            "explain",
            "Show top 5 invoices",
            "--tables",
            "dt_invoice,dt_customer",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert "LIMIT 5" in payload["plan"]["sql"]
    assert payload["plan"]["limit"] == 5
    assert payload["plan"]["tables"] == ["dt_invoice"]


def test_query_explain_unknown_table_rejected(project_path: Path):
    result = runner.invoke(
        app,
        [
            "query",
            "explain",
            "How many secrets are there?",
            "--tables",
            "dt_invoice",
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert any("allowlist" in v for v in payload["plan"]["violations"])


def test_query_explain_unknown_verb_rejected(project_path: Path):
    result = runner.invoke(
        app,
        ["query", "explain", "Forecast next quarter's invoices", "--json"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert any("no matching rule" in v for v in payload["plan"]["violations"])


def test_query_explain_human_output(project_path: Path):
    result = runner.invoke(app, ["query", "explain", "List all invoices"])
    assert result.exit_code == 0
    assert "SELECT * FROM dt_invoice" in result.output


# ---------------------------------------------------------------------------
# Cross-cutting: --json contract
# ---------------------------------------------------------------------------


def test_query_run_json_envelope(project_path: Path):
    """Every payload under --json parses and contains an ``ok`` boolean."""
    result = runner.invoke(app, ["query", "run", "invoice_count", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "ok" in payload
    assert isinstance(payload["ok"], bool)


def test_query_explain_json_envelope(project_path: Path):
    result = runner.invoke(
        app,
        ["query", "explain", "Total amount for invoices", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "ok" in payload
    assert "plan" in payload
