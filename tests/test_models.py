"""Milestone 4 — the residency-aware, engagement-typed model layer (design.md Section 7; R6.3/R7).

All hermetic: a fake HTTP transport stands in for Ollama/DeepSeek, so routing, the no-real->cloud
invariant, retry/fallback, and single-tenant residency are all exercised with no network or GPU.
"""

from __future__ import annotations

import pytest

from saltpilot.models import (
    Completion,
    DeepSeekV4Provider,
    OllamaProvider,
    ProviderUnavailable,
    ResidencyManager,
    Role,
    RoutedProvider,
    build_model_provider,
)

ANALYSIS_MODEL = "foundation-sec-8b-reasoning"
LOCAL_REASONER = "qwen3-4b-thinking-2507"
CLOUD_REASONER = "deepseek-v4-flash"


class FakePost:
    """Records calls; can be programmed to fail chat calls whose URL contains a substring."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._fail: dict[str, tuple[int, bool]] = {}  # substr -> (remaining, retryable)

    def program_fail(self, substr: str, times: int = 10**9, retryable: bool = True):
        self._fail[substr] = (times, retryable)

    def chat_calls(self, substr: str) -> int:
        return sum(1 for url, _ in self.calls if substr in url and url.endswith("/chat/completions"))

    def __call__(self, url, headers, payload, timeout):
        self.calls.append((url, payload))
        if url.endswith("/chat/completions"):
            for substr, (remaining, retryable) in list(self._fail.items()):
                if substr in url and remaining > 0:
                    self._fail[substr] = (remaining - 1, retryable)
                    raise ProviderUnavailable(f"programmed fail {substr}", retryable=retryable)
        model = payload.get("model", "?")
        return 200, {"model": model, "choices": [{"message": {"content": f"answer from {model}"}}], "usage": {"total_tokens": 3}}


def _no_sleep(_):
    pass


# ------------------------------------------------------------------ role routing

def test_analysis_is_always_local_even_on_practice(make_engagement, tmp_path):
    post = FakePost()
    routed = build_model_provider(make_engagement(tmp_path, kind="practice"),
                                  http_post=post, deepseek_api_key="k", sleep=_no_sleep)
    c = routed.complete(Role.ANALYSIS, "interpret this")
    assert c.provider == "ollama"
    assert c.model == ANALYSIS_MODEL
    assert post.chat_calls("deepseek") == 0  # analysis never touches the cloud


def test_reasoning_on_practice_uses_cloud_teacher(make_engagement, tmp_path):
    post = FakePost()
    routed = build_model_provider(make_engagement(tmp_path, kind="practice"),
                                  http_post=post, deepseek_api_key="k", sleep=_no_sleep)
    assert routed.reasoning_route == "cloud-teacher"
    c = routed.complete(Role.REASONING, "what next?")
    assert c.provider == "deepseek-v4"
    assert c.model == CLOUD_REASONER
    assert c.fell_back is False


def test_reasoning_on_real_uses_local_support(make_engagement, tmp_path):
    post = FakePost()
    routed = build_model_provider(make_engagement(tmp_path, kind="real"), http_post=post)
    assert routed.reasoning_route == "local-support"
    c = routed.complete(Role.REASONING, "what next?")
    assert c.provider == "ollama"
    assert c.model == LOCAL_REASONER


# ------------------------------------------------------------------ R7.4: no real -> cloud

def test_real_engagement_never_constructs_a_cloud_provider(make_engagement, tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "should-be-ignored-on-real")
    routed = build_model_provider(make_engagement(tmp_path, kind="real"), http_post=FakePost())
    assert routed._reasoner_cloud is None


def test_real_engagement_makes_no_external_call(make_engagement, tmp_path):
    post = FakePost()
    routed = build_model_provider(make_engagement(tmp_path, kind="real"), http_post=post)
    routed.complete(Role.ANALYSIS, "x")
    routed.complete(Role.REASONING, "y")
    assert all("deepseek" not in url for url, _ in post.calls)  # nothing leaves the box


def test_routedprovider_refuses_cloud_on_real(make_engagement, tmp_path):
    eng = make_engagement(tmp_path, kind="real")
    local = OllamaProvider(LOCAL_REASONER, http_post=FakePost())
    poison = DeepSeekV4Provider(CLOUD_REASONER, api_key="k", http_post=FakePost())
    with pytest.raises(ValueError):
        RoutedProvider(eng, analysis=local, reasoner_local=local, reasoner_cloud=poison)


# ------------------------------------------------------------------ R6.3: cloud fallback

def test_cloud_failure_falls_back_to_local_and_records_it(make_engagement, tmp_path):
    post = FakePost()
    post.program_fail("deepseek")  # cloud always fails
    routed = build_model_provider(make_engagement(tmp_path, kind="practice"),
                                  http_post=post, deepseek_api_key="k", sleep=_no_sleep, cloud_retries=2)
    c = routed.complete(Role.REASONING, "what next?")
    assert c.provider == "ollama"            # answered locally
    assert c.model == LOCAL_REASONER
    assert c.fell_back is True
    assert "cloud unavailable" in (c.fallback_reason or "")
    assert post.chat_calls("deepseek") == 3  # cloud tried retries+1 times before falling back


def test_non_retryable_cloud_error_does_not_retry(make_engagement, tmp_path):
    post = FakePost()
    post.program_fail("deepseek", retryable=False)
    routed = build_model_provider(make_engagement(tmp_path, kind="practice"),
                                  http_post=post, deepseek_api_key="k", sleep=_no_sleep, cloud_retries=3)
    c = routed.complete(Role.REASONING, "q")
    assert c.fell_back is True
    assert post.chat_calls("deepseek") == 1  # tried once, no retries


def test_practice_without_key_uses_local_and_flags_it(make_engagement, tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    routed = build_model_provider(make_engagement(tmp_path, kind="practice"), http_post=FakePost())
    assert routed._reasoner_cloud is None
    assert routed.reasoning_route == "local-support"
    c = routed.complete(Role.REASONING, "q")
    assert c.provider == "ollama" and c.fell_back is True


# ------------------------------------------------------------------ R7.1: single-tenant residency

def test_residency_manager_evicts_on_swap():
    unloaded = []
    rm = ResidencyManager()
    rm.acquire("A", unload=lambda: unloaded.append("A"))
    rm.acquire("A")             # same model -> no swap
    assert rm.resident == "A" and rm.swaps == 0 and unloaded == []
    rm.acquire("B", unload=lambda: unloaded.append("B"))
    assert rm.resident == "B" and rm.swaps == 1 and unloaded == ["A"]


def test_real_run_swaps_local_models_once(make_engagement, tmp_path):
    rm = ResidencyManager()
    routed = build_model_provider(make_engagement(tmp_path, kind="real"), http_post=FakePost(), residency=rm)
    routed.complete(Role.ANALYSIS, "x")     # foundation-sec resident
    assert rm.resident == ANALYSIS_MODEL and rm.swaps == 0
    routed.complete(Role.REASONING, "y")    # qwen3 -> swap
    assert rm.resident == LOCAL_REASONER and rm.swaps == 1


def test_practice_keeps_only_one_local_model_resident(make_engagement, tmp_path):
    rm = ResidencyManager()
    routed = build_model_provider(make_engagement(tmp_path, kind="practice"),
                                  http_post=FakePost(), deepseek_api_key="k", sleep=_no_sleep, residency=rm)
    routed.complete(Role.ANALYSIS, "x")     # local foundation-sec
    routed.complete(Role.REASONING, "y")    # cloud -> no local residency change
    assert rm.resident == ANALYSIS_MODEL and rm.swaps == 0


# ------------------------------------------------------------------ OpenAI-compat transport

def test_provider_parses_openai_response():
    c = DeepSeekV4Provider(CLOUD_REASONER, api_key="k", http_post=FakePost()).complete(Role.REASONING, "hi")
    assert c.text == f"answer from {CLOUD_REASONER}"
    assert c.usage == {"total_tokens": 3}


def test_provider_maps_http_500_to_unavailable():
    def boom(url, headers, payload, timeout):
        return 500, {}
    with pytest.raises(ProviderUnavailable):
        OllamaProvider(ANALYSIS_MODEL, http_post=boom).complete(Role.ANALYSIS, "hi")


def test_provider_maps_missing_choices_to_unavailable():
    def empty(url, headers, payload, timeout):
        return 200, {"model": "x"}  # no choices
    with pytest.raises(ProviderUnavailable):
        OllamaProvider(ANALYSIS_MODEL, http_post=empty).complete(Role.ANALYSIS, "hi")
