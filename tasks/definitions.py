"""
Task definitions for the sequential CrewAI pipeline.

Each Task's `context` list points at the prior task(s), which is how
CrewAI feeds one agent's output into the next agent's prompt. The order
of `tasks` returned here is also the execution order under
Process.sequential (see main.py).
"""

from pathlib import Path

from crewai import Agent, Task

REPO_ROOT = Path(__file__).resolve().parent.parent


def build_tasks(agents: dict[str, Agent]) -> list[Task]:
    requirements_text = (REPO_ROOT / "requirements.md").read_text()

    risk_analysis_task = Task(
        description=(
            "Read the following requirements document for the SauceDemo "
            "login + checkout flow and identify the highest-risk areas to "
            "test. Rank the top 6-10 risks by (likely impact x likelihood), "
            "and briefly justify each.\n\n"
            "--- REQUIREMENTS DOCUMENT ---\n"
            f"{requirements_text}\n"
            "--- END REQUIREMENTS DOCUMENT ---"
        ),
        expected_output=(
            "A ranked list of 6-10 risks. For each: a short title, the "
            "requirement ID(s) it relates to, why it's risky, and a "
            "High/Medium/Low severity rating."
        ),
        agent=agents["risk_analyst"],
    )

    test_design_task = Task(
        description=(
            "Using the risk list from the Risk Analyst, write concrete "
            "test scenarios in Given/When/Then format. Cover the top risks, "
            "include at least one negative/edge case scenario per major "
            "risk area (auth failures, validation errors, error_user "
            "checkout issues), and reference which risk each scenario "
            "addresses. Aim for 8-12 focused scenarios rather than an "
            "exhaustive list."
        ),
        expected_output=(
            "A numbered list of Given/When/Then scenarios, each tagged "
            "with the risk it covers and a short scenario name suitable "
            "for use as a test function name."
        ),
        agent=agents["test_designer"],
        context=[risk_analysis_task],
    )

    automation_task = Task(
        description=(
            "Convert the Given/When/Then scenarios from the Test Designer "
            "into runnable Playwright Python test code targeting "
            "https://www.saucedemo.com. Requirements for the code:\n"
            "- Use pytest + Playwright's sync API (`from playwright.sync_api "
            "import Page, expect`), with test functions taking a `page` "
            "fixture (pytest-playwright provides it).\n"
            "- Use the standard_user / secret_sauce credentials for happy-"
            "path scenarios, and the other seeded accounts "
            "(locked_out_user, error_user, etc.) for the negative scenarios "
            "that call for them, exactly as documented on SauceDemo's own "
            "login page.\n"
            "- Prefer role/text/test-id locators over brittle CSS/XPath.\n"
            "- Group related scenarios into one or two files.\n"
            "- Use the 'Save Playwright test file' tool to write each file "
            "to the tests/ directory. Do not just print the code -- "
            "actually call the tool."
        ),
        expected_output=(
            "Confirmation of each test file written to tests/, plus a "
            "short summary of which scenarios map to which test functions."
        ),
        agent=agents["automation_engineer"],
        context=[test_design_task],
    )

    failure_analysis_task = Task(
        description=(
            "Run the full Playwright suite using the 'Run Playwright test "
            "suite' tool. Then, for every failing or erroring test in the "
            "results, write a concise root-cause hypothesis grounded in the "
            "actual error message/stack trace (e.g. bad locator, real "
            "product defect on saucedemo.com, timing/flakiness, "
            "environment/setup issue). If the suite is fully green, say so "
            "plainly -- do not invent issues."
        ),
        expected_output=(
            "The overall pass/fail totals, and for each failing test: its "
            "name, the error summary, and your root-cause hypothesis with "
            "a suggested next step."
        ),
        agent=agents["failure_analyst"],
        context=[automation_task],
    )

    reporting_task = Task(
        description=(
            "Synthesize everything so far -- the risk analysis, the test "
            "scenarios, what was automated, and the failure analysis -- "
            "into a release-quality report. Include: an executive summary, "
            "a coverage summary (risks covered vs total), pass/fail totals, "
            "the top open risks (including any test failures found), and a "
            "clear GO / NO-GO recommendation with reasoning. Produce both:\n"
            "1. A Markdown version.\n"
            "2. A standalone HTML version (self-contained, minimal inline "
            "CSS, no external assets) suitable for GitHub Pages.\n"
            "Use the 'Write release report' tool to save both -- do not "
            "just print them."
        ),
        expected_output=(
            "Confirmation that reports/release_report.md and docs/index.html "
            "were written, plus the go/no-go verdict stated in your final "
            "answer."
        ),
        agent=agents["release_reporter"],
        context=[risk_analysis_task, test_design_task, automation_task, failure_analysis_task],
    )

    return [
        risk_analysis_task,
        test_design_task,
        automation_task,
        failure_analysis_task,
        reporting_task,
    ]
