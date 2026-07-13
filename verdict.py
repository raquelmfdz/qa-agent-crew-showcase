"""
Single source of truth for the Release Reporter's GO/NO-GO verdict
vocabulary.

Two places need to recognize the same verdict strings in different
surfaces -- main.py parses the raw Markdown for the GitHub step-summary
callout, agents/tools.py parses the rendered HTML for the badge -- so the
token list lives here once. Adding a third verdict value only means
changing it in one place.
"""

VERDICT_TOKENS = r"NO-GO|GO"
