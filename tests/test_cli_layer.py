"""CLI smoke tests for `dhow layer *` subapp.

Each command must support `--json` and return a JSON payload; the subapp
delegates to ``dhow.core.layers`` for validation and merging.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from dhow_cli.main import app
from dhow_cli.scaffold import scaffold_project

runner = CliRunner()


def _scaffold_and_chdir(tmp_path: Path) -> Path:
    project_path = scaffold_project("demo", tmp_path / "demo")
    os.chdir(project_path)
    return project_path


def _build_project(tmp_path: Path) -> Path:
    """Scaffold and build so the registry has the demo Invoice DocType."""
    project_path = _scaffold_and_chdir(tmp_path)
    build = runner.invoke(app, ["build"])
    assert build.exit_code == 0, build.output
    return project_path


def _retarget_layer(name: str, target: str) -> Path:
    """Rewrite the scaffolded layer's target to a real DocType in the registry."""
    layer_path = Path.cwd() / "layers" / f"{name}.json"
    body = json.loads(layer_path.read_text(encoding="utf-8"))
    body["target"] = target
    layer_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return layer_path


def _parse_layer_json(output: str) -> dict:
    """Helper: find the last JSON object in CLI output and parse it."""
    text = output.strip()
    decoder = json.JSONDecoder()
    idx = 0
    last: dict | None = None
    while idx < len(text):
        while idx < len(text) and text[idx] in " \n\r\t":
            idx += 1
        if idx >= len(text):
            break
        obj, end = decoder.raw_decode(text, idx)
        if isinstance(obj, dict):
            last = obj
        idx = end
    assert last is not None, f"no JSON object found in output: {output!r}"
    return last


def test_layer_help_lists_commands():
    result = runner.invoke(app, ["layer", "--help"])
    assert result.exit_code == 0
    for cmd in ("new", "diff", "export", "validate"):
        assert cmd in result.output


def test_layer_new_creates_skeleton(tmp_path: Path):
    project_path = _scaffold_and_chdir(tmp_path)

    result = runner.invoke(
        app, ["layer", "new", "tenant_a", "--base-version", "1", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is True
    assert payload["name"] == "tenant_a"
    assert payload["target"] == "tenant_a"
    assert payload["base_version"] == "1"
    layer_file = project_path / "layers" / "tenant_a.json"
    assert layer_file.exists()
    body = json.loads(layer_file.read_text(encoding="utf-8"))
    assert body["name"] == "tenant_a"
    assert body["target"] == "tenant_a"
    assert body["base_version"] == "1"
    assert body["kind"] == "tenant"
    assert body["add_fields"] == []


def test_layer_new_rejects_existing_file(tmp_path: Path):
    _scaffold_and_chdir(tmp_path)
    layers_dir = Path.cwd() / "layers"
    layers_dir.mkdir(parents=True, exist_ok=True)
    (layers_dir / "tenant_a.json").write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app, ["layer", "new", "tenant_a", "--base-version", "1", "--json"]
    )
    assert result.exit_code == 1
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is False
    assert "already exists" in payload["error"]


def test_layer_new_without_json_prints_human(tmp_path: Path):
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["layer", "new", "tenant_b", "--base-version", "2"])
    assert result.exit_code == 0
    assert "Created layer tenant_b" in result.output


def test_layer_diff_on_built_project(tmp_path: Path):
    """A skeleton layer targeting an existing DocType produces no drift."""
    _build_project(tmp_path)
    runner.invoke(app, ["layer", "new", "tenant_c", "--base-version", "1", "--json"])
    _retarget_layer("tenant_c", "Invoice")

    result = runner.invoke(app, ["layer", "diff", "tenant_c", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is True
    assert payload["layer"] == "tenant_c"
    assert payload["target"] == "Invoice"
    assert payload["added"] == []
    assert payload["removed"] == []
    assert payload["changed"] == []
    assert payload["has_drift"] is False


def test_layer_diff_reports_missing_file(tmp_path: Path):
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["layer", "diff", "ghost", "--json"])
    assert result.exit_code == 1
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_layer_export_writes_artifact(tmp_path: Path):
    project_path = _build_project(tmp_path)
    runner.invoke(app, ["layer", "new", "tenant_d", "--base-version", "1", "--json"])
    _retarget_layer("tenant_d", "Invoice")

    out_path = project_path / "build" / "tenant_d.artifact.json"
    result = runner.invoke(
        app,
        ["layer", "export", "tenant_d", "-o", str(out_path), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is True
    assert payload["layer"] == "tenant_d"
    assert payload["target"] == "Invoice"
    assert out_path.exists()
    artifact = json.loads(out_path.read_text(encoding="utf-8"))
    assert "layer" in artifact
    assert "merged_registry" in artifact
    assert artifact["layer"]["name"] == "tenant_d"


def test_layer_export_rejects_missing_layer(tmp_path: Path):
    _scaffold_and_chdir(tmp_path)
    out_path = Path.cwd() / "missing.json"
    result = runner.invoke(
        app, ["layer", "export", "ghost", "-o", str(out_path), "--json"]
    )
    assert result.exit_code == 1
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_layer_validate_with_no_layers(tmp_path: Path):
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["layer", "validate", "--json"])
    assert result.exit_code == 0
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["layers"] == 0


def test_layer_validate_after_build_passes(tmp_path: Path):
    """With a built registry, a skeleton layer targeting Invoice is valid."""
    _build_project(tmp_path)
    create = runner.invoke(
        app, ["layer", "new", "invoice_tenant", "--base-version", "1", "--json"]
    )
    assert create.exit_code == 0, create.output
    _retarget_layer("invoice_tenant", "Invoice")

    result = runner.invoke(app, ["layer", "validate", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert len(payload["layers"]) == 1
    assert payload["layers"][0]["name"] == "invoice_tenant"
    assert payload["layers"][0]["target"] == "Invoice"


def test_layer_validate_detects_unknown_target(tmp_path: Path):
    """A layer whose target is absent from the registry must report an error."""
    _build_project(tmp_path)
    runner.invoke(app, ["layer", "new", "ghost_layer", "--base-version", "1", "--json"])
    # Leave the scaffolded target as-is: "ghost_layer" — no such DocType.

    result = runner.invoke(app, ["layer", "validate", "--json"])
    assert result.exit_code == 1
    payload = _parse_layer_json(result.output)
    assert payload["ok"] is False
    assert any("ghost_layer" in err for err in payload["errors"])


def test_layer_validate_human_output(tmp_path: Path):
    _scaffold_and_chdir(tmp_path)
    result = runner.invoke(app, ["layer", "validate"])
    assert result.exit_code == 0
    assert "No layers found" in result.output
