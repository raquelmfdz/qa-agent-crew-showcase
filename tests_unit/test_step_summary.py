"""
Unit tests for the GitHub Actions job-summary writer (main.py). These
lock in the exact format expected on the run's Summary page: one
collapsed section per agent, plus a standalone GO/NO-GO callout that
doesn't require expanding anything.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from main import _extract_verdict_callout, _write_github_step_summary


class TestExtractVerdictCallout:
    def test_extracts_go_and_its_reasoning(self) -> None:
        text = "Report body...\n\n## GO / NO-GO Recommendation\n\n**GO**\n\nAll flows pass, ship it."
        result = _extract_verdict_callout(text)
        assert result.startswith("## ✅ GO")
        assert "All flows pass, ship it." in result

    def test_extracts_nogo_and_its_reasoning(self) -> None:
        text = "**NO-GO**\n\nCritical checkout bug found."
        result = _extract_verdict_callout(text)
        assert result.startswith("## 🛑 NO-GO")
        assert "Critical checkout bug found." in result

    def test_falls_back_gracefully_when_no_verdict_is_found(self) -> None:
        result = _extract_verdict_callout("A report with no bolded verdict anywhere.")
        assert "Could not detect a GO/NO-GO verdict" in result


class TestWriteGithubStepSummary:
    def _fake_result(self) -> SimpleNamespace:
        return SimpleNamespace(
            tasks_output=[
                SimpleNamespace(agent="QA Risk Analyst", raw="risks..."),
                SimpleNamespace(agent="Test Designer", raw="scenarios..."),
                SimpleNamespace(agent="Automation Engineer", raw="wrote tests..."),
                SimpleNamespace(agent="Failure Analyst", raw="10 passed, 2 failed"),
                SimpleNamespace(agent="Release Reporter", raw="**GO**\n\nShip it."),
            ]
        )

    def test_is_a_noop_when_not_running_in_github_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        # Must not raise even with a result that would break file writing
        # if this path were accidentally taken.
        _write_github_step_summary(SimpleNamespace(tasks_output=None))

    def test_writes_one_collapsed_section_per_agent_plus_a_verdict_callout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        _write_github_step_summary(self._fake_result())

        content = summary_file.read_text()
        assert content.count("<details>") == 5
        assert content.count("<details open>") == 0
        assert "<summary><strong>Release Reporter</strong></summary>" in content
        assert "## ✅ GO" in content
        # The callout must come after every collapsed section.
        assert content.index("## ✅ GO") > content.rindex("</details>")
