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
import re
import time
from typing import Any

from crewai import LLM, BaseLLM
from pydantic import PrivateAttr

from config.models import (
    MAX_RETRIES_PER_PROVIDER,
    PIN_COOLDOWN_SECONDS,
    PROVIDER_CHAIN,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_BACKOFF_SECONDS,
    ProviderConfig,
)

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


# How a failure is handled: retried in place, immediately demoted to the
# next provider, or re-raised as a genuine bug.
_FAILURE_TRANSIENT = "transient"
_FAILURE_PERMANENT = "permanent"
_FAILURE_FATAL = "fatal"

# litellm's exception mapping (used for the Groq/Ollama path) and the
# google-genai SDK (used for Gemini) both attach the real HTTP-ish status
# to every mapped/API error -- `status_code` and `code` respectively. That
# is a far more reliable signal than message text, so it's checked first.
# Message-substring matching below only kicks in for exceptions that carry
# neither attribute (e.g. a raw socket error before any SDK gets to wrap
# it).
_TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_PERMANENT_STATUS_CODES = frozenset({401, 403, 404})


def _status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _compile_marker(marker: str) -> re.Pattern[str]:
    # Bare numeric markers ("500", "429", ...) are \b-bounded so they don't
    # match inside an unrelated number like "1500 tokens" or "500ms" -- a
    # plain substring check used to do exactly that. Phrase markers stay
    # unbounded so inflected forms ("rate limited") still match.
    pattern = rf"\b{re.escape(marker)}\b" if marker.isdigit() else re.escape(marker)
    return re.compile(pattern, re.IGNORECASE)


def _compile_markers(*markers: str) -> tuple[re.Pattern[str], ...]:
    return tuple(_compile_marker(m) for m in markers)


# Transient: retried in place first, then falls through if retries are
# exhausted. Free-tier models get overloaded ("high demand") far more
# often than dedicated paid capacity, so these need to recover gracefully,
# not crash the whole pipeline.
_TRANSIENT_MARKERS = _compile_markers(
    "rate limit",
    "rate_limit",
    "ratelimit",
    "429",
    "quota",
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
    "temporary",
    "timed out",
    "connection error",
    "connection reset",
)

# Permanent: retrying the same provider can't fix a bad key or a
# deprecated model, so these skip straight to the next provider.
# Deliberately narrow -- generic words like "not found" or "timeout" also
# show up in genuine application bugs (e.g. a KeyError message, an
# assertion on a 404-shaped fixture) and would silently swallow those as
# "recoverable" instead of surfacing them.
_PERMANENT_MARKERS = _compile_markers(
    "401",
    "403",
    "404",
    "authentication",
    "unauthorized",
    "api key",
    "invalid_api_key",
    "model_not_found",
)


def _classify_failure(exc: Exception) -> str:
    status_code = _status_code(exc)
    if status_code is not None:
        if status_code in _TRANSIENT_STATUS_CODES:
            return _FAILURE_TRANSIENT
        if status_code in _PERMANENT_STATUS_CODES:
            return _FAILURE_PERMANENT
        return _FAILURE_FATAL

    message = str(exc)
    if any(pattern.search(message) for pattern in _TRANSIENT_MARKERS):
        return _FAILURE_TRANSIENT
    if any(pattern.search(message) for pattern in _PERMANENT_MARKERS):
        return _FAILURE_PERMANENT
    return _FAILURE_FATAL


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
    # monotonic() timestamp of the last time we advanced _active_index past
    # 0. None means we're on the preferred (first) provider.
    _pinned_at: float | None = PrivateAttr(default=None)

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
        self._pinned_at = None

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

        if (
            self._active_index > 0
            and self._pinned_at is not None
            and time.monotonic() - self._pinned_at >= PIN_COOLDOWN_SECONDS
        ):
            logger.info(
                "%.0fs since falling back; giving '%s' another chance before "
                "the rest of the chain.",
                PIN_COOLDOWN_SECONDS,
                self._providers[0][0].name,
            )
            self._active_index = 0
            self._pinned_at = None

        for offset in range(len(self._providers) - self._active_index):
            index = self._active_index + offset
            provider_cfg, llm = self._providers[index]
            attempt = 0
            while True:
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
                        self._pinned_at = time.monotonic()
                        self.model = llm.model
                    return result
                except Exception as exc:  # noqa: BLE001 - intentionally broad, see module docstring
                    last_error = exc
                    classification = _classify_failure(exc)

                    if classification == _FAILURE_FATAL:
                        # Not a fallthrough-worthy error (e.g. a genuine bug) -- re-raise.
                        raise

                    if classification == _FAILURE_TRANSIENT and attempt < MAX_RETRIES_PER_PROVIDER:
                        attempt += 1
                        backoff = RETRY_BACKOFF_SECONDS * attempt
                        logger.warning(
                            "Provider '%s' (%s) failed transiently (%s). "
                            "Retrying in %.1fs (attempt %d/%d)...",
                            provider_cfg.name,
                            provider_cfg.model,
                            exc,
                            backoff,
                            attempt,
                            MAX_RETRIES_PER_PROVIDER,
                        )
                        time.sleep(backoff)
                        continue

                    logger.warning(
                        "Provider '%s' (%s) failed (%s). Falling back to next provider...",
                        provider_cfg.name,
                        provider_cfg.model,
                        exc,
                    )
                    break

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
