"""CLI smoke tests for `dhow skill *` subapp.

Each command must support ``--json`` and return a structured payload; the
subapp delegates to ``dhow.skills`` for parsing and search.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from dhow_cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


POSTING_SKILL = """---
name: posting-rules
version: 1.0.0
description: Posting rules for sales invoices.
triggers:
  - post an invoice
examples:
  - question: How do I post a sales invoice?
    answer: Use the Sales Invoice submit action.
constraints:
  - do not post out-of-period entries
---

# Posting Rules

## Sales Invoices
Use the standard submit action. Always reconcile with the delivery note.
"""

CLOSE_SKILL = """---
name: close-period
version: 0.2.0
description: Period close playbook.
triggers:
  - close the books
constraints:
  - never close an unlocked period
---

# Period Close

## Pre-close Checklist
- Reconcile all bank accounts
"""


def _setup_skills_dir(tmp_path: Path) -> Path:
    """Create a project root with ``skills/`` containing two SKILL.md files."""
    project_root = tmp_path / "proj"
    skills_dir = project_root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "posting-rules.md").write_text(POSTING_SKILL, encoding="utf-8")
    (skills_dir / "close-period.md").write_text(CLOSE_SKILL, encoding="utf-8")
    os.chdir(project_root)
    return project_root


def _parse_json(output: str) -> dict:
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


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


def test_skill_help_lists_commands():
    result = runner.invoke(app, ["skill", "--help"])
    assert result.exit_code == 0, result.output
    for cmd in ("list", "show"):
        assert cmd in result.output


# ---------------------------------------------------------------------------
# list — empty
# ---------------------------------------------------------------------------


def test_skill_list_with_no_directory_returns_empty_payload(tmp_path: Path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    os.chdir(project_root)
    result = runner.invoke(app, ["skill", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["skills"] == []


def test_skill_list_with_empty_skills_dir_returns_empty(tmp_path: Path):
    project_root = tmp_path / "proj"
    (project_root / "skills").mkdir(parents=True, exist_ok=True)
    os.chdir(project_root)
    result = runner.invoke(app, ["skill", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["skills"] == []


# ---------------------------------------------------------------------------
# list — populated
# ---------------------------------------------------------------------------


def test_skill_list_returns_structured_list(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["ok"] is True
    assert payload["count"] == 2
    names = [s["name"] for s in payload["skills"]]
    assert names == ["close-period", "posting-rules"]
    posting = next(s for s in payload["skills"] if s["name"] == "posting-rules")
    assert posting["version"] == "1.0.0"
    assert posting["description"] == "Posting rules for sales invoices."
    assert "post an invoice" in posting["triggers"]
    assert "do not post out-of-period entries" in posting["constraints"]
    assert isinstance(posting["examples"], list) and posting["examples"]
    # Progressive-disclosure contract: list view excludes full body.
    assert "content" not in posting


def test_skill_list_human_output_prints_summary(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "list"])
    assert result.exit_code == 0, result.output
    assert "Skills (2)" in result.output
    assert "posting-rules" in result.output
    assert "close-period" in result.output
    assert "Posting rules for sales invoices." in result.output


def test_skill_list_no_skills_human_output(tmp_path: Path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    os.chdir(project_root)
    result = runner.invoke(app, ["skill", "list"])
    assert result.exit_code == 0
    assert "No skills found" in result.output


# ---------------------------------------------------------------------------
# list — query and limit
# ---------------------------------------------------------------------------


def test_skill_list_with_query_filters_by_keyword(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(
        app, ["skill", "list", "--query", "playbook", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["query"] == "playbook"
    names = [s["name"] for s in payload["skills"]]
    assert names == ["close-period"]


def test_skill_list_with_query_against_name_token(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "list", "-q", "posting", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert [s["name"] for s in payload["skills"]] == ["posting-rules"]


def test_skill_list_with_limit_caps_results(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "list", "--limit", "1", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["count"] == 1
    assert payload["limit"] == 1
    assert len(payload["skills"]) == 1


def test_skill_list_with_no_match_returns_empty_skills(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(
        app, ["skill", "list", "--query", "nothingmatches", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["ok"] is True
    assert payload["skills"] == []
    assert payload["count"] == 0


# ---------------------------------------------------------------------------
# list — malformed skill
# ---------------------------------------------------------------------------


def test_skill_list_reports_malformed_skill(tmp_path: Path):
    project_root = tmp_path / "proj"
    skills_dir = project_root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "broken.md").write_text("no frontmatter here", encoding="utf-8")
    os.chdir(project_root)
    result = runner.invoke(app, ["skill", "list", "--json"])
    assert result.exit_code == 1
    payload = _parse_json(result.output)
    assert payload["ok"] is False
    assert payload["errors"]
    assert "frontmatter" in payload["errors"][0]


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_skill_show_returns_full_body_json(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "show", "posting-rules", "--json"])
    assert result.exit_code == 0, result.output
    payload = _parse_json(result.output)
    assert payload["ok"] is True
    assert payload["skill"]["name"] == "posting-rules"
    assert payload["skill"]["version"] == "1.0.0"
    assert "Sales Invoices" in payload["content"]
    assert "delivery note" in payload["content"]


def test_skill_show_human_output_prints_sections(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "show", "close-period"])
    assert result.exit_code == 0, result.output
    assert "# close-period (v0.2.0)" in result.output
    assert "Period close playbook." in result.output
    assert "Triggers:" in result.output
    assert "close the books" in result.output
    assert "Constraints:" in result.output
    assert "never close an unlocked period" in result.output
    assert "## Pre-close Checklist" in result.output


def test_skill_show_unknown_skill_reports_error(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "show", "ghost", "--json"])
    assert result.exit_code == 1
    payload = _parse_json(result.output)
    assert payload["ok"] is False
    assert "ghost" in payload["error"]
    assert payload["name"] == "ghost"


def test_skill_show_unknown_skill_human_output(tmp_path: Path):
    _setup_skills_dir(tmp_path)
    result = runner.invoke(app, ["skill", "show", "ghost"])
    assert result.exit_code == 1
    assert "unknown skill" in result.output


def test_skill_show_without_skills_directory(tmp_path: Path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    os.chdir(project_root)
    result = runner.invoke(app, ["skill", "show", "anything", "--json"])
    assert result.exit_code == 1
    payload = _parse_json(result.output)
    assert payload["ok"] is False
    assert "no skills directory" in payload["error"]


def test_skill_show_rejects_malformed_skill(tmp_path: Path):
    project_root = tmp_path / "proj"
    skills_dir = project_root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "broken.md").write_text("missing frontmatter", encoding="utf-8")
    os.chdir(project_root)
    result = runner.invoke(app, ["skill", "show", "broken", "--json"])
    assert result.exit_code == 1
    payload = _parse_json(result.output)
    assert payload["ok"] is False
    assert "frontmatter" in payload["error"]
