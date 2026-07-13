"""
Unit tests for the report-rendering and file-writing tools agents call
(agents/tools.py). These are plain functions wrapped by CrewAI's @tool
decorator -- calling `.func(...)` invokes the underlying Python function
directly, bypassing the agent/LLM layer entirely.
"""

from pathlib import Path

import agents.tools as tools_module
from agents.tools import _render_report_html, save_playwright_test, write_release_report


class TestRenderReportHtml:
    def test_wraps_body_in_the_fixed_styled_template(self) -> None:
        html = _render_report_html("# Title\n\nSome text.")
        assert html.strip().startswith("<!doctype html>")
        assert "<style>" in html
        assert "<h1>Title</h1>" in html

    def test_renders_markdown_tables(self) -> None:
        html = _render_report_html("| a | b |\n|---|---|\n| 1 | 2 |\n")
        assert "<table>" in html
        assert "<td>1</td>" in html

    def test_highlights_go_verdict_as_a_badge(self) -> None:
        html = _render_report_html("## Recommendation\n\n**GO**\n\nShip it.")
        assert '<span class="verdict verdict-go">GO</span>' in html

    def test_highlights_nogo_verdict_as_a_badge(self) -> None:
        html = _render_report_html("## Recommendation\n\n**NO-GO**\n\nDo not ship.")
        assert '<span class="verdict verdict-nogo">NO-GO</span>' in html

    def test_only_the_first_verdict_mention_becomes_a_badge(self) -> None:
        # A report that says "GO" once as the verdict and then repeats the
        # word in prose shouldn't turn every mention into a pill badge.
        html = _render_report_html("**GO**\n\nWe say GO because **GO** means ship.")
        assert html.count('class="verdict') == 1


class TestSavePlaywrightTest:
    def test_rejects_filenames_that_would_break_pytest_discovery(self) -> None:
        result = save_playwright_test.func(filename="checkout.py", code="def test_x(): pass")
        assert "Rejected" in result

    def test_writes_a_valid_filename_to_the_tests_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(tools_module, "TESTS_DIR", tmp_path / "tests")
        monkeypatch.setattr(tools_module, "REPO_ROOT", tmp_path)

        result = save_playwright_test.func(filename="test_new.py", code="def test_x(): pass")

        written = tmp_path / "tests" / "test_new.py"
        assert written.exists()
        assert written.read_text() == "def test_x(): pass"
        assert "test_new.py" in result


class TestWriteReleaseReport:
    def test_writes_both_markdown_and_rendered_html(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(tools_module, "REPORTS_DIR", tmp_path / "reports")
        monkeypatch.setattr(tools_module, "DOCS_DIR", tmp_path / "docs")
        monkeypatch.setattr(tools_module, "REPO_ROOT", tmp_path)

        write_release_report.func(markdown_content="# Report\n\n**GO**\n\nAll clear.")

        md_path = tmp_path / "reports" / "release_report.md"
        html_path = tmp_path / "docs" / "index.html"
        assert md_path.read_text() == "# Report\n\n**GO**\n\nAll clear."
        assert "verdict-go" in html_path.read_text()
