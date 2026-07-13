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
import sys

from crewai import Crew, Process
from dotenv import load_dotenv

from agents.definitions import build_agents
from tasks.definitions import build_tasks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("qa_agent_crew")


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
