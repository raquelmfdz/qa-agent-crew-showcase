"""
LLM factory: builds a CrewAI-compatible LLM object that tries providers
in the order defined by config.models.PROVIDER_CHAIN, skipping any
provider whose API key isn't set in the environment.

Why this exists: free tiers rate-limit aggressively and occasionally
deprecate models without notice. Hardcoding a single provider means the
whole crew dies the moment that provider hiccups. Instead we wrap CrewAI's
LLM in a small proxy that catches auth/rate-limit/model errors on the
FIRST call and retries with the next provider in the chain.

This is intentionally simple (not a generic retry framework) -- it's a
showcase project, so the goal is "obviously correct and easy to read",
not "handles every conceivable failure mode".
"""

import logging
import os
from typing import Any

from crewai import LLM, BaseLLM
from pydantic import PrivateAttr

from config.models import PROVIDER_CHAIN, REQUEST_TIMEOUT_SECONDS, ProviderConfig

logger = logging.getLogger(__name__)

# CrewAI tags messages with an internal "cache_breakpoint" bookkeeping key
# for providers that support prompt caching (e.g. Anthropic). Native
# provider classes (like Gemini's) strip it before sending; the generic
# LiteLLM-routed path that Groq goes through does not (as of crewai
# 1.15.x), so Groq's strict message-schema validation rejects the request
# with a 400. We strip it ourselves so every provider in the chain gets a
# clean message list regardless of upstream provider-specific bugs.
_CACHE_BREAKPOINT_KEY = "cache_breakpoint"


def _strip_cache_breakpoint(messages: Any) -> Any:
    if not isinstance(messages, list):
        return messages
    return [
        {k: v for k, v in msg.items() if k != _CACHE_BREAKPOINT_KEY}
        if isinstance(msg, dict)
        else msg
        for msg in messages
    ]


# Substrings that identify a "try the next provider" failure. CrewAI/LiteLLM
# wrap provider SDK exceptions, so we match on message content rather than
# exception type to stay robust across providers.
_FALLTHROUGH_MARKERS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "429",
    "quota",
    "authentication",
    "unauthorized",
    "401",
    "403",
    "api key",
    "invalid_api_key",
    "model_not_found",
    "does not exist",
    "not found",
    "404",
    # Transient server-side outages -- exactly what a fallback chain is
    # for. Free-tier models get overloaded ("high demand") far more often
    # than dedicated paid capacity, so these need to fall through too,
    # not crash the whole pipeline.
    "503",
    "502",
    "500",
    "unavailable",
    "overloaded",
    "high demand",
    "internal error",
    "server error",
    "try again later",
    "temporarily",
    "timeout",
    "timed out",
    "connection error",
    "connection reset",
)


class FallbackLLM(BaseLLM):
    """A CrewAI `BaseLLM` that transparently falls back across providers on
    failure.

    CrewAI's `Agent.llm` field is pydantic-validated to require a `BaseLLM`
    instance (or a plain string), so this must be a real `BaseLLM` subclass
    -- a duck-typed proxy object is rejected at `Agent(...)` construction
    time. We subclass `BaseLLM` and delegate `call()` to whichever
    underlying provider `LLM` is currently active, advancing to the next
    one in the chain on a fallthrough-worthy failure.
    """

    _providers: list[tuple[ProviderConfig, LLM]] = PrivateAttr()
    _active_index: int = PrivateAttr(default=0)

    def __init__(self, available: list[tuple[ProviderConfig, LLM]]) -> None:
        if not available:
            raise RuntimeError(
                "No LLM providers are available. Set at least one of "
                "GEMINI_API_KEY or GROQ_API_KEY (see .env.example), or run "
                "a local Ollama daemon."
            )
        _, first_llm = available[0]
        super().__init__(model=first_llm.model)
        self._providers = available
        self._active_index = 0

    def call(
        self,
        messages: Any,
        tools: list[dict[str, Any]] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> Any:
        last_error: Exception | None = None
        clean_messages = _strip_cache_breakpoint(messages)

        for offset in range(len(self._providers) - self._active_index):
            index = self._active_index + offset
            provider_cfg, llm = self._providers[index]
            try:
                result = llm.call(
                    clean_messages,
                    tools=tools,
                    callbacks=callbacks,
                    available_functions=available_functions,
                    from_task=from_task,
                    from_agent=from_agent,
                    response_model=response_model,
                )
                if index != self._active_index:
                    logger.warning(
                        "LLM fallback: now using '%s' (%s) after earlier "
                        "provider failure.",
                        provider_cfg.name,
                        provider_cfg.model,
                    )
                    self._active_index = index
                    self.model = llm.model
                return result
            except Exception as exc:  # noqa: BLE001 - intentionally broad, see module docstring
                message = str(exc).lower()
                is_falls_through = any(marker in message for marker in _FALLTHROUGH_MARKERS)
                last_error = exc
                if is_falls_through:
                    logger.warning(
                        "Provider '%s' (%s) failed (%s). Falling back to next provider...",
                        provider_cfg.name,
                        provider_cfg.model,
                        exc,
                    )
                    continue
                # Not a fallthrough-worthy error (e.g. a genuine bug) -- re-raise.
                raise

        raise RuntimeError(
            f"All configured LLM providers failed. Last error: {last_error}"
        )


def _build_llm(provider: ProviderConfig) -> LLM:
    kwargs: dict[str, Any] = {
        "model": provider.model,
        "timeout": REQUEST_TIMEOUT_SECONDS,
    }
    if provider.api_key_env:
        kwargs["api_key"] = os.environ[provider.api_key_env]
    return LLM(**kwargs)


def get_llm() -> FallbackLLM:
    """Build the fallback-chain LLM from whichever providers currently have
    credentials available in the environment.

    Ollama is included whenever no key-based provider is configured, since
    it needs no key -- if the local daemon isn't running either, the first
    real call will fail with a clear connection error.
    """
    available: list[tuple[ProviderConfig, LLM]] = []

    for provider in PROVIDER_CHAIN:
        has_key = provider.api_key_env is None or bool(os.environ.get(provider.api_key_env))
        if not has_key:
            logger.info(
                "Skipping provider '%s': env var %s is not set (%s)",
                provider.name,
                provider.api_key_env,
                provider.free_tier_note,
            )
            continue
        available.append((provider, _build_llm(provider)))

    if not available:
        raise RuntimeError(
            "No LLM providers configured. Set GEMINI_API_KEY and/or "
            "GROQ_API_KEY (see .env.example), or run a local Ollama daemon "
            "for llama3.1."
        )

    logger.info(
        "LLM fallback chain: %s",
        " -> ".join(p.name for p, _ in available),
    )
    return FallbackLLM(available)
