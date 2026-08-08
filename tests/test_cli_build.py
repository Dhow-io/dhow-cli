"""Tests for `dhow build` / `dhow diff` integration through the project loader."""

from pathlib import Path

from dhow.cli.build import run_build, run_diff
from dhow.cli.scaffold import scaffold_project
from dhow.core.project import Project


def test_build_emits_artifacts(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    project = Project(project_path)
    result = run_build(project)
    assert result["ok"] is True
    assert "paths" in result
    assert project.registry_path.exists()


def test_build_check_detects_drift(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    project = Project(project_path)
    run_build(project)
    check = run_build(project, check=True)
    assert check["ok"] is True


def test_diff_reports_additions(tmp_path: Path):
    project_path = scaffold_project("demo", tmp_path / "demo")
    project = Project(project_path)
    # Initial build writes registry
    run_build(project)
    # Add a new DocType file
    (project_path / "modules" / "doctypes" / "item.py").write_text(
        "from dhow import DocType, field\n\n"
        "class Item(DocType):\n"
        "    name = field.Text(required=True)\n"
    )
    diff = run_diff(project)
    assert "Item" in diff["added"]
