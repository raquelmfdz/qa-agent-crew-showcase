"""
Unit tests for the LLM fallback chain (llm/factory.py).

This is the one piece of custom logic the whole pipeline depends on, and
it's had real bugs surface in live runs -- a rejected Agent.llm type, a
provider-specific message-schema incompatibility, and a missing
transient-error marker. Each of those became a regression test here so
they can't silently come back after a crewai/litellm upgrade.

Deliberately separate from tests/ -- that directory is reserved for the
generated Playwright suite against SauceDemo, and is what
agents/tools.py's run_playwright_suite() executes and hands to the
Failure Analyst. Mixing unit tests in there would pollute that report.
"""

from unittest.mock import MagicMock

import pytest
from crewai import LLM

from config.models import ProviderConfig
from llm.factory import FallbackLLM, _strip_cache_breakpoint, get_llm


def _provider(name: str, model: str) -> ProviderConfig:
    return ProviderConfig(name=name, model=model, api_key_env=None, free_tier_note="n/a")


def _mock_llm(model: str) -> MagicMock:
    mock = MagicMock(spec=LLM)
    mock.model = model
    return mock


class TestStripCacheBreakpoint:
    def test_removes_key_from_every_message(self) -> None:
        messages = [
            {"role": "system", "content": "sys", "cache_breakpoint": True},
            {"role": "user", "content": "hi", "cache_breakpoint": True},
        ]
        cleaned = _strip_cache_breakpoint(messages)
        assert all("cache_breakpoint" not in m for m in cleaned)
        assert cleaned[0]["content"] == "sys"
        assert cleaned[1]["content"] == "hi"

    def test_leaves_messages_without_the_key_untouched(self) -> None:
        messages = [{"role": "assistant", "content": "hello"}]
        assert _strip_cache_breakpoint(messages) == messages

    def test_passes_through_non_list_input_unchanged(self) -> None:
        assert _strip_cache_breakpoint("a plain string prompt") == "a plain string prompt"


class TestFallbackLLM:
    def test_requires_at_least_one_provider(self) -> None:
        with pytest.raises(RuntimeError, match="No LLM providers are available"):
            FallbackLLM([])

    def test_uses_first_provider_when_it_succeeds(self) -> None:
        gemini = _mock_llm("gemini-flash-latest")
        gemini.call.return_value = "gemini answer"
        groq = _mock_llm("groq/llama-3.3-70b-versatile")

        fb = FallbackLLM([(_provider("gemini", gemini.model), gemini), (_provider("groq", groq.model), groq)])
        result = fb.call("hi")

        assert result == "gemini answer"
        assert fb._active_index == 0
        groq.call.assert_not_called()

    @pytest.mark.parametrize(
        "error_text",
        [
            "Error code: 429 - rate limit exceeded",
            "401 Unauthorized: invalid api key",
            # Real error text from a live run: Gemini free-tier overload.
            "google.genai.errors.ServerError: 503 UNAVAILABLE. {'message': "
            "'This model is currently experiencing high demand. Spikes in "
            "demand are usually temporary. Please try again later.'}",
        ],
    )
    def test_falls_through_to_next_provider_on_recoverable_errors(self, error_text: str) -> None:
        first = _mock_llm("first/model")
        first.call.side_effect = Exception(error_text)
        second = _mock_llm("second/model")
        second.call.return_value = "second provider handled it"

        fb = FallbackLLM([(_provider("first", first.model), first), (_provider("second", second.model), second)])
        result = fb.call("hi")

        assert result == "second provider handled it"
        assert fb._active_index == 1
        assert fb.model == "second/model"

    def test_does_not_fall_through_on_a_genuine_bug(self) -> None:
        first = _mock_llm("first/model")
        first.call.side_effect = TypeError("unexpected keyword argument 'foo'")
        second = _mock_llm("second/model")

        fb = FallbackLLM([(_provider("first", first.model), first), (_provider("second", second.model), second)])

        with pytest.raises(TypeError, match="unexpected keyword argument"):
            fb.call("hi")
        second.call.assert_not_called()

    def test_raises_when_every_provider_fails(self) -> None:
        first = _mock_llm("first/model")
        first.call.side_effect = Exception("429 rate limited")
        second = _mock_llm("second/model")
        second.call.side_effect = Exception("503 unavailable")

        fb = FallbackLLM([(_provider("first", first.model), first), (_provider("second", second.model), second)])

        with pytest.raises(RuntimeError, match="All configured LLM providers failed"):
            fb.call("hi")

    def test_strips_cache_breakpoint_before_delegating_to_provider(self) -> None:
        # Regression test: Groq's strict schema validation rejects
        # CrewAI's internal "cache_breakpoint" bookkeeping key with a 400.
        provider_llm = _mock_llm("groq/llama-3.3-70b-versatile")
        provider_llm.call.return_value = "ok"

        fb = FallbackLLM([(_provider("groq", provider_llm.model), provider_llm)])
        fb.call([{"role": "system", "content": "sys", "cache_breakpoint": True}])

        sent_messages = provider_llm.call.call_args.args[0]
        assert all("cache_breakpoint" not in m for m in sent_messages)

    def test_sticks_with_the_provider_it_fell_back_to_on_the_next_call(self) -> None:
        first = _mock_llm("first/model")
        first.call.side_effect = Exception("429 rate limited")
        second = _mock_llm("second/model")
        second.call.return_value = "handled"

        fb = FallbackLLM([(_provider("first", first.model), first), (_provider("second", second.model), second)])
        fb.call("first call")
        first.call.reset_mock()

        fb.call("second call")

        first.call.assert_not_called()
        assert second.call.call_count == 2


class TestGetLlm:
    def test_skips_providers_without_an_api_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        fb = get_llm()

        # Ollama needs no key, so it's always in the chain as the last
        # resort -- gemini/groq are skipped when their keys are unset.
        assert len(fb._providers) == 1
        assert fb._providers[0][0].name == "ollama"

    def test_builds_chain_in_provider_order_when_keys_are_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setenv("GROQ_API_KEY", "fake-key")

        fb = get_llm()

        names = [cfg.name for cfg, _ in fb._providers]
        assert names == ["gemini", "groq", "ollama"]
