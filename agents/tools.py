"""
Custom CrewAI tools shared by the crew's agents.

Kept deliberately small and dependency-light: each tool does one concrete
filesystem or subprocess action (write a test file, run the Playwright
suite, write a report) so agents can take real actions instead of just
producing text that a human would have to act on manually.
"""

import json
import re
import subprocess
from pathlib import Path

import markdown as md
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


# A small free-tier model asked to freehand a "self-contained HTML page
# with inline CSS" tends to produce bare, unstyled markup -- it's an LLM,
# not a designer. Rather than trust that, the agent only writes Markdown;
# we render it through one fixed, already-designed template here, so every
# report looks the same regardless of which provider in the fallback
# chain wrote the content.
_VERDICT_PATTERN = re.compile(r"<(?:strong|b)>\s*(NO-GO|GO)\s*</(?:strong|b)>", re.IGNORECASE)

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>QA Release Report — SauceDemo Login &amp; Checkout</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #ffffff;
    --fg: #1a1a1a;
    --muted: #5a5a5a;
    --border: #e0e0e0;
    --code-bg: rgba(127, 127, 127, 0.15);
    --go-fg: #1a7f37;
    --go-bg: #e6f4ea;
    --nogo-fg: #b42318;
    --nogo-bg: #fbe9e7;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1117;
      --fg: #e6edf3;
      --muted: #9aa4af;
      --border: #30363d;
      --go-fg: #3fb950;
      --go-bg: #10261a;
      --nogo-fg: #ff7b72;
      --nogo-bg: #2d1614;
    }
  }
  body {
    margin: 0;
    padding: 2.5rem 1.25rem 4rem;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }
  main {
    max-width: 780px;
    margin: 0 auto;
  }
  h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
  h2 {
    font-size: 1.1rem;
    margin-top: 2.25rem;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem;
  }
  h3 { font-size: 1rem; margin-top: 1.5rem; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
    margin: 0.75rem 0 1.5rem;
  }
  th, td {
    text-align: left;
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid var(--border);
  }
  th { color: var(--muted); font-weight: 600; }
  code {
    background: var(--code-bg);
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    font-size: 0.9em;
  }
  pre {
    background: var(--code-bg);
    border-radius: 8px;
    padding: 1rem;
    overflow-x: auto;
  }
  pre code { background: none; padding: 0; }
  blockquote {
    margin: 1rem 0;
    padding: 0.1rem 1.1rem;
    border-left: 3px solid var(--border);
    color: var(--muted);
  }
  ul, ol { padding-left: 1.25rem; }
  .verdict {
    display: inline-block;
    font-weight: 700;
    letter-spacing: 0.02em;
    border-radius: 999px;
    padding: 0.3rem 1rem;
    margin: 0.5rem 0 1rem;
  }
  .verdict-go { color: var(--go-fg); background: var(--go-bg); }
  .verdict-nogo { color: var(--nogo-fg); background: var(--nogo-bg); }
  footer {
    margin-top: 3rem;
    color: var(--muted);
    font-size: 0.85rem;
    border-top: 1px solid var(--border);
    padding-top: 1rem;
  }
</style>
</head>
<body>
<main>
__BODY__
<footer>Generated by the qa-agent-crew Release Reporter agent.</footer>
</main>
</body>
</html>
"""


def _highlight_verdict(body_html: str) -> str:
    def _replace(match: re.Match) -> str:
        verdict = match.group(1).upper()
        css_class = "verdict-go" if verdict == "GO" else "verdict-nogo"
        return f'<span class="verdict {css_class}">{verdict}</span>'

    # Only the first GO/NO-GO mention becomes the headline badge; later
    # mentions in body text are left as plain emphasis.
    return _VERDICT_PATTERN.sub(_replace, body_html, count=1)


def _render_report_html(markdown_content: str) -> str:
    body_html = md.markdown(markdown_content, extensions=["tables", "fenced_code"])
    body_html = _highlight_verdict(body_html)
    return _HTML_TEMPLATE.replace("__BODY__", body_html)


@tool("Write release report")
def write_release_report(markdown_content: str) -> str:
    """Write the final release report as Markdown, and auto-generate a
    matching styled HTML version for GitHub Pages.

    Markdown goes to reports/release_report.md (for the repo/PR reader).
    The HTML version is rendered from that same Markdown through a fixed
    site template (not written by the agent) and saved to docs/index.html.

    Args:
        markdown_content: Full Markdown report body -- executive summary,
            coverage, pass/fail totals, top risks, and a GO/NO-GO
            recommendation (bold the verdict, e.g. "**GO**", so it renders
            as a highlighted badge).
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    md_path = REPORTS_DIR / "release_report.md"
    html_path = DOCS_DIR / "index.html"

    md_path.write_text(markdown_content)
    html_path.write_text(_render_report_html(markdown_content))

    return (
        f"Wrote report to {md_path.relative_to(REPO_ROOT)} and "
        f"{html_path.relative_to(REPO_ROOT)}"
    )
