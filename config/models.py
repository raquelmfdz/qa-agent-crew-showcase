"""
Single source of truth for LLM provider/model configuration.

Free-tier model names and availability change fairly often, so every
model ID used by this project lives HERE and nowhere else. If a model
gets deprecated or renamed on a provider's free tier, update it in one
place.

Provider order = fallback order. The LLM factory (llm/factory.py) walks
this list top to bottom and uses the first provider that has credentials
available AND doesn't error out (rate limit / auth / model-not-found).

In GitHub Actions, only GEMINI and GROQ will realistically be available,
since OLLAMA requires a locally running daemon. OLLAMA is kept in the
chain as a last-resort, local-only fallback for developers running the
crew on their own machine.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    # CrewAI/LiteLLM-style model string, e.g. "gemini/gemini-2.5-flash"
    model: str
    # Name of the env var holding the API key for this provider.
    # None for providers that don't need a key (e.g. local Ollama).
    api_key_env: str | None
    # Human hint printed in logs/README about where to get a free key.
    free_tier_note: str


# Order matters: this IS the fallback chain, top = tried first.
PROVIDER_CHAIN: list[ProviderConfig] = [
    ProviderConfig(
        name="gemini",
        # "-latest" alias: Google hot-swaps this to the current recommended
        # Flash model (with a 2-week deprecation notice before any swap),
        # so we don't have to chase dated model IDs like "gemini-2.5-flash"
        # every time Google sunsets one for new users.
        model="gemini/gemini-flash-latest",
        api_key_env="GEMINI_API_KEY",
        free_tier_note="Free key at https://aistudio.google.com/app/apikey",
    ),
    ProviderConfig(
        name="groq",
        model="groq/llama-3.3-70b-versatile",
        api_key_env="GROQ_API_KEY",
        free_tier_note="Free key at https://console.groq.com/keys",
    ),
    ProviderConfig(
        name="ollama",
        model="ollama/llama3.1",
        api_key_env=None,  # local daemon, no key needed
        free_tier_note=(
            "Local-only: install Ollama (https://ollama.com) and run "
            "`ollama pull llama3.1`. Not available in GitHub Actions."
        ),
    ),
]

# Reasonable defaults so a single slow/rate-limited call can't hang the
# whole pipeline forever. Kept small since this is a showcase, not prod.
REQUEST_TIMEOUT_SECONDS = 60

# How many extra attempts a transient failure (rate limit, 5xx, timeout) on
# the CURRENT provider gets before the fallback chain advances to the next
# one. A 429 often clears within a couple seconds, so it's usually cheaper
# to retry in place than to jump providers. Non-transient failures (auth,
# model-not-found) skip retries entirely -- see llm/factory.py.
MAX_RETRIES_PER_PROVIDER = 1
RETRY_BACKOFF_SECONDS = 2.0

# Once the chain has fallen through to a later provider, how long to stay
# "pinned" there before giving the earlier, preferred provider another
# chance. Without this, a single transient failure early in a long run
# permanently demotes the preferred provider even after it recovers.
PIN_COOLDOWN_SECONDS = 60.0
