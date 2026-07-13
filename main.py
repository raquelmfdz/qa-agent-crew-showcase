#!/usr/bin/env python3
"""
Entrypoint for the qa-agent-crew pipeline.

Runs the five agents (Risk Analyst -> Test Designer -> Automation Engineer
-> Failure Analyst -> Release Reporter) as a sequential CrewAI crew. Each
agent's output feeds the next via the `context` links set up in
tasks/definitions.py.

Usage:
    python main.py

Requires at least one of GEMINI_API_KEY / GROQ_API_KEY to be set (or a
local Ollama daemon running) -- see .env.example and README.md.
"""

import logging
import os
import re
import sys
from typing import Any

from crewai import Crew, Process
from dotenv import load_dotenv

from agents.definitions import build_agents
from tasks.definitions import build_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("qa_agent_crew")

# Matches the Release Reporter's isolated "**GO**" / "**NO-GO**" verdict
# (see tasks/definitions.py, which requires the verdict be bolded on its
# own with nothing else inside the bold markers).
_MD_VERDICT_PATTERN = re.compile(r"\*\*\s*(NO-GO|GO)\s*\*\*", re.IGNORECASE)


def _extract_verdict_callout(release_reporter_raw: str) -> str:
    """Pull the GO/NO-GO verdict + its immediate reasoning out of the
    Release Reporter's output, for a quick, always-visible callout that
    doesn't require expanding any section to read.
    """
    match = _MD_VERDICT_PATTERN.search(release_reporter_raw)
    if not match:
        return (
            "_Could not detect a GO/NO-GO verdict -- see the Release "
            "Reporter section above for the full report._"
        )

    verdict = match.group(1).upper()
    emoji = "✅" if verdict == "GO" else "🛑"
    reasoning = release_reporter_raw[match.end() :].lstrip("\n ").split("\n\n", 1)[0].strip()

    callout = f"## {emoji} {verdict}"
    if reasoning:
        callout += f"\n\n{reasoning}"
    return callout


def _write_github_step_summary(result: Any) -> None:
    """Write each agent's output to the GitHub Actions job summary page.

    GITHUB_STEP_SUMMARY is a file path GitHub Actions sets for every step;
    anything appended to it renders as Markdown on the run's Summary tab,
    so the 5 agents' answers are readable without opening the raw logs.
    It's only set on Actions runners -- a no-op for local runs.

    All 5 agent answers are collapsed by default so the page doesn't flood
    the screen; the GO/NO-GO verdict is pulled out into its own
    non-collapsible callout at the end for quick feedback at a glance.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path or not result.tasks_output:
        return

    sections = ["# QA Agent Crew -- Run Summary\n"]
    for task_output in result.tasks_output:
        sections.append(
            f"<details>\n<summary><strong>{task_output.agent}</strong></summary>\n\n"
            f"{task_output.raw}\n\n</details>\n"
        )

    sections.append("---\n")
    sections.append(_extract_verdict_callout(result.tasks_output[-1].raw))

    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(sections))
            f.write("\n")
    except OSError as exc:
        logger.warning("Could not write GitHub step summary: %s", exc)


def main() -> int:
    load_dotenv()  # picks up .env locally; no-op in CI, where secrets are real env vars

    try:
        agents = build_agents()
    except RuntimeError as exc:
        logger.error("Could not initialize LLM providers: %s", exc)
        logger.error(
            "Set GEMINI_API_KEY and/or GROQ_API_KEY (see .env.example), "
            "or run a local Ollama daemon."
        )
        return 1

    tasks = build_tasks(agents)

    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    logger.info("Starting qa-agent-crew pipeline (5 agents, sequential)...")
    try:
        result = crew.kickoff()
    except Exception:
        logger.exception("Pipeline failed unexpectedly.")
        return 1

    logger.info("Pipeline finished.")
    print("\n=== Final Release Reporter output ===\n")
    print(result)
    print(
        "\nReports written to reports/release_report.md and docs/index.html "
        "(if the Release Reporter agent completed successfully)."
    )
    _write_github_step_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
