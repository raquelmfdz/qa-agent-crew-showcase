"""
Custom CrewAI tools shared by the crew's agents.

Kept deliberately small and dependency-light: each tool does one concrete
filesystem or subprocess action (write a test file, run the Playwright
suite, write a report) so agents can take real actions instead of just
producing text that a human would have to act on manually.
"""

import json
import subprocess
from pathlib import Path

from crewai.tools import tool

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"
REPORTS_DIR = REPO_ROOT / "reports"
DOCS_DIR = REPO_ROOT / "docs"


@tool("Save Playwright test file")
def save_playwright_test(filename: str, code: str) -> str:
    """Save generated Playwright Python test code to the tests/ directory.

    Args:
        filename: File name for the test, e.g. 'test_generated_checkout.py'.
            Must start with 'test_' and end with '.py' so pytest discovers it.
        code: The full contents of the Python test file.

    Returns:
        A confirmation message with the path the file was written to.
    """
    if not filename.startswith("test_") or not filename.endswith(".py"):
        return (
            f"Rejected filename '{filename}': must start with 'test_' and "
            "end with '.py' for pytest discovery."
        )
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TESTS_DIR / filename
    path.write_text(code)
    return f"Saved test file to {path.relative_to(REPO_ROOT)}"


@tool("Run Playwright test suite")
def run_playwright_suite() -> str:
    """Run the full pytest/Playwright suite in tests/ and capture JSON +
    JUnit XML results to reports/. Returns a JSON summary (pass/fail counts
    and per-test outcomes) for the Failure Analyst to reason over.

    Never raises on test failure -- a red suite is a valid, expected result
    that the pipeline needs to analyze, not a crash.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_report_path = REPORTS_DIR / "results.json"
    junit_path = REPORTS_DIR / "results.xml"

    cmd = [
        "python",
        "-m",
        "pytest",
        str(TESTS_DIR),
        f"--json-report",
        f"--json-report-file={json_report_path}",
        f"--junitxml={junit_path}",
        "-v",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Playwright suite timed out after 900s"})
    except FileNotFoundError as exc:
        return json.dumps({"error": f"Could not run pytest: {exc}"})

    summary: dict = {
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-2000:],
    }

    if json_report_path.exists():
        try:
            report = json.loads(json_report_path.read_text())
            summary["totals"] = report.get("summary", {})
            summary["tests"] = [
                {
                    "nodeid": t.get("nodeid"),
                    "outcome": t.get("outcome"),
                    "message": (t.get("call") or {}).get("longrepr", "")[:1500],
                }
                for t in report.get("tests", [])
            ]
        except (json.JSONDecodeError, OSError) as exc:
            summary["json_report_error"] = str(exc)
    else:
        summary["json_report_error"] = "No JSON report was produced."

    return json.dumps(summary, indent=2)


@tool("Write release report")
def write_release_report(markdown_content: str, html_content: str) -> str:
    """Write the final release report as both Markdown and HTML.

    Markdown goes to reports/release_report.md (for the repo/PR reader).
    HTML goes to docs/index.html so it can be served for free via
    GitHub Pages straight from the repo's docs/ folder.

    Args:
        markdown_content: Full Markdown report body.
        html_content: Full standalone HTML document (including <html> tags).
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    md_path = REPORTS_DIR / "release_report.md"
    html_path = DOCS_DIR / "index.html"

    md_path.write_text(markdown_content)
    html_path.write_text(html_content)

    return (
        f"Wrote report to {md_path.relative_to(REPO_ROOT)} and "
        f"{html_path.relative_to(REPO_ROOT)}"
    )
