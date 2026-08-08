"""CLI smoke tests using Typer CliRunner."""

from pathlib import Path

from typer.testing import CliRunner

from dhow_cli.main import app
from dhow_cli.scaffold import scaffold_project

runner = CliRunner()


def test_init_command(tmp_path: Path):
    result = runner.invoke(app, ["init", "demo", "--path", str(tmp_path), "--json"])
    assert result.exit_code == 0
    assert "demo" in result.output
    assert (tmp_path / "demo" / "dhow.toml").exists()


def test_build_command(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    result = runner.invoke(app, ["build", "--json"])
    assert result.exit_code == 0
    assert "ok" in result.output


def test_diff_command(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    runner.invoke(app, ["build"])
    result = runner.invoke(app, ["diff", "--json"])
    assert result.exit_code == 0
    assert "added" in result.output


def test_describe_command(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    runner.invoke(app, ["build"])
    result = runner.invoke(app, ["describe", "Invoice", "--json"])
    assert result.exit_code == 0
    assert "Invoice" in result.output


def test_schema_search_command(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    runner.invoke(app, ["build"])
    result = runner.invoke(app, ["schema", "number", "--json"])
    assert result.exit_code == 0
    assert "Invoice.number" in result.output


def test_new_doctype_command(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    result = runner.invoke(app, ["new", "doctype", "Item", "--json"])
    assert result.exit_code == 0
    assert (project_path / "modules" / "doctypes" / "item.py").exists()


def test_doctor_command(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    import os

    os.chdir(project_path)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    assert "ok" in result.output
