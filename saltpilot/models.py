"""The model layer — residency-aware, engagement-typed routing (Milestone 4; design.md Section 7).

One `ModelProvider` interface, two concrete backends (local Ollama, cloud DeepSeek V4), and a
`RoutedProvider` policy wrapper that picks the backend by *role* and *engagement kind*:

    role = ANALYSIS   -> local Ollama (Foundation-Sec)        [always local, both modes, R4/R7.1]
    role = REASONING  -> chosen by engagement.kind, NOT convenience:
        kind == 'practice' (lab/CTF/HTB/THM) -> DeepSeek V4    [the cloud TEACHER, R7.3]
        kind == 'real'     (authorized IRL)  -> local reasoner [SUPPORT, private, R7.4]

Two invariants this module enforces in *code*, not just config:

  * **No real engagement ever reaches the cloud (R7.4).** A `RoutedProvider` for a `real`
    engagement refuses to even hold a cloud provider (constructor raises), and `build_model_provider`
    never constructs one — so "nothing leaves the box" is structural, not a promise.
  * **Single-tenant local GPU (R7.1).** Local backends share one `ResidencyManager`; requesting a
    second local model unloads the first, so at most one local model is ever resident.

Cloud calls get a bounded retry + timeout, then fall back to the local reasoner, recording which
reasoner actually answered (R6.3). Circuit-breaker/backoff hardening is the long-haul slice.

The HTTP transport is stdlib `urllib` by default and injectable (`http_post`) for tests, so the
whole routing/fallback/residency contract is exercised with no network, model, or GPU.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Protocol, runtime_checkable

# An HTTP transport: (url, headers, json_payload, timeout) -> (status_code, response_dict).
HttpPost = Callable[[str, dict, dict, float], "tuple[int, dict]"]

DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_DEEPSEEK_URL = "https://api.deepseek.com/v1"


class Role(str, Enum):
    ANALYSIS = "analysis"      # interpretation of findings (v1: always local Foundation-Sec)
    REASONING = "reasoning"    # the copilot's answer (routed by engagement kind)


# --------------------------------------------------------------------------- errors
class ProviderError(Exception):
    """A model call failed."""


class ProviderUnavailable(ProviderError):
    """The backend was unreachable / errored — triggers retry (if retryable) then fallback."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


# --------------------------------------------------------------------------- result
@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    provider: str                       # 'ollama' | 'deepseek-v4'
    role: Role
    fell_back: bool = False             # a cloud->local degrade happened (R6.3)
    fallback_reason: str | None = None
    usage: dict | None = None


# --------------------------------------------------------------------------- transport
def _default_http_post(url: str, headers: dict, payload: dict, timeout: float) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as exc:
        # 5xx is transient/retryable; 4xx is a request/auth problem (not worth retrying, still
        # falls back so recon/copilot degrades rather than fails).
        raise ProviderUnavailable(f"HTTP {exc.code}", retryable=exc.code >= 500) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable(f"transport error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProviderUnavailable(f"malformed response: {exc}", retryable=False) from exc


def _native_base(base_url: str) -> str:
    """Strip a trailing `/v1` so we can reach Ollama's native API (for keep_alive control)."""
    b = base_url.rstrip("/")
    if b.endswith("/v1"):
        b = b[:-3]
    return b.rstrip("/")


def _extract_text(resp: dict) -> str:
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderUnavailable(f"no completion in response: {exc!r}", retryable=False) from exc


# --------------------------------------------------------------------------- residency
class ResidencyManager:
    """Single-tenant local GPU (R7.1): at most one local model resident at a time.

    Ollama itself evicts via keep_alive, but the arbiter guarantees we never *ask* two local models
    to co-reside: acquiring model B while A is resident unloads A first. v1 is sequential, so this
    plus the shared instance is the whole guarantee; concurrent inference is a later slice.
    """

    def __init__(self) -> None:
        self._resident: str | None = None
        self._unload: Callable[[], None] | None = None
        self._lock = threading.Lock()
        self.swaps = 0                  # observability: how many evictions happened

    def acquire(self, model: str, unload: Callable[[], None] | None = None) -> None:
        with self._lock:
            if self._resident == model:
                if unload is not None:      # same model still resident; refresh its unloader
                    self._unload = unload
                return
            if self._resident is not None:  # a different model is resident -> evict it
                if self._unload is not None:
                    try:
                        self._unload()
                    except Exception:
                        pass                # best-effort eviction; never break the pipeline
                self.swaps += 1
            self._resident = model
            self._unload = unload

    def release(self) -> None:
        with self._lock:
            if self._unload is not None:
                try:
                    self._unload()
                except Exception:
                    pass
            self._resident = None
            self._unload = None

    @property
    def resident(self) -> str | None:
        return self._resident


# --------------------------------------------------------------------------- providers
@runtime_checkable
class ModelProvider(Protocol):
    def complete(self, role: Role, prompt: str, *, max_tokens: int = ..., system: str | None = ...) -> Completion: ...


class _OpenAICompatProvider:
    """Shared OpenAI-compatible `/v1/chat/completions` client (Ollama and DeepSeek both speak it)."""

    provider_name = "openai-compat"

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        temperature: float | None = None,
        http_post: HttpPost | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self._http_post = http_post or _default_http_post

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _chat(self, prompt: str, max_tokens: int, system: str | None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "stream": False}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        url = f"{self.base_url}/chat/completions"
        status, resp = self._http_post(url, self._headers(), payload, self.timeout)
        if status != 200:
            raise ProviderUnavailable(f"HTTP {status}", retryable=status >= 500)
        return resp

    def complete(self, role: Role, prompt: str, *, max_tokens: int = 1024, system: str | None = None) -> Completion:
        resp = self._chat(prompt, max_tokens, system)
        return Completion(
            text=_extract_text(resp),
            model=resp.get("model") or self.model,
            provider=self.provider_name,
            role=role,
            usage=resp.get("usage"),
        )


class OllamaProvider(_OpenAICompatProvider):
    """Local, on-demand model served by Ollama (R4.3, R7.1). Participates in single-tenant GPU."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        api_key: str | None = "ollama",     # Ollama ignores it; the OpenAI client wants one
        timeout: float = 120.0,
        residency: ResidencyManager | None = None,
        keep_alive: str | int = "5m",
        http_post: HttpPost | None = None,
    ) -> None:
        super().__init__(model, base_url=base_url, api_key=api_key, timeout=timeout, http_post=http_post)
        self._residency = residency
        self._keep_alive = keep_alive

    def unload(self) -> None:
        """Best-effort VRAM release via Ollama's native keep_alive=0 (belt-and-suspenders)."""
        url = f"{_native_base(self.base_url)}/api/generate"
        try:
            self._http_post(url, self._headers(), {"model": self.model, "keep_alive": 0}, 10.0)
        except Exception:
            pass

    def complete(self, role: Role, prompt: str, *, max_tokens: int = 1024, system: str | None = None) -> Completion:
        if self._residency is not None:
            self._residency.acquire(self.model, unload=self.unload)  # single-tenant handshake first
        return super().complete(role, prompt, max_tokens=max_tokens, system=system)


class DeepSeekV4Provider(_OpenAICompatProvider):
    """Hosted DeepSeek V4 — the cloud TEACHER, used only on `practice` engagements (R7.3).

    Off-box: consumes no local VRAM and never participates in residency.
    """

    provider_name = "deepseek-v4"

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_DEEPSEEK_URL,
        api_key: str | None = None,
        timeout: float = 60.0,
        http_post: HttpPost | None = None,
    ) -> None:
        super().__init__(model, base_url=base_url, api_key=api_key, timeout=timeout, http_post=http_post)


# --------------------------------------------------------------------------- router
def _default_backoff(attempt: int) -> float:
    return 0.5 * (2 ** attempt)


class RoutedProvider:
    """Policy wrapper: route by role + engagement kind, with cloud->local fallback on practice.

    Enforces R7.4 structurally: a `real` engagement may not hold a cloud provider at all.
    """

    def __init__(
        self,
        engagement,
        *,
        analysis: ModelProvider,
        reasoner_local: ModelProvider,
        reasoner_cloud: ModelProvider | None = None,
        cloud_retries: int = 2,
        sleep: Callable[[float], None] | None = None,
        backoff: Callable[[int], float] | None = None,
    ) -> None:
        if getattr(engagement, "kind", None) == "real" and reasoner_cloud is not None:
            # There is NO configuration that sends a real engagement to the cloud (R7.4).
            raise ValueError("a 'real' engagement must not be given a cloud reasoner (R7.4)")
        self.engagement = engagement
        self._analysis = analysis
        self._reasoner_local = reasoner_local
        self._reasoner_cloud = reasoner_cloud
        self._cloud_retries = cloud_retries
        self._sleep = sleep or __import__("time").sleep
        self._backoff = backoff or _default_backoff

    @property
    def reasoning_route(self) -> str:
        """'cloud-teacher' | 'local-support' — how REASONING resolves for this engagement."""
        if self.engagement.kind == "practice" and self._reasoner_cloud is not None:
            return "cloud-teacher"
        return "local-support"

    def complete(self, role: Role, prompt: str, *, max_tokens: int = 1024, system: str | None = None) -> Completion:
        if role is Role.ANALYSIS:
            return self._analysis.complete(role, prompt, max_tokens=max_tokens, system=system)
        if role is Role.REASONING:
            if self.engagement.kind == "real":
                return self._reasoner_local.complete(role, prompt, max_tokens=max_tokens, system=system)
            return self._reason_practice(prompt, max_tokens, system)
        raise ValueError(f"unknown role: {role!r}")

    def _reason_practice(self, prompt: str, max_tokens: int, system: str | None) -> Completion:
        if self._reasoner_cloud is None:
            # practice, but no teacher configured (e.g. no API key) -> local, recorded as a degrade
            c = self._reasoner_local.complete(Role.REASONING, prompt, max_tokens=max_tokens, system=system)
            return replace(c, fell_back=True, fallback_reason="no cloud teacher configured")

        last: Exception | None = None
        for attempt in range(self._cloud_retries + 1):
            try:
                return self._reasoner_cloud.complete(Role.REASONING, prompt, max_tokens=max_tokens, system=system)
            except ProviderError as exc:
                last = exc
                if not getattr(exc, "retryable", True) or attempt == self._cloud_retries:
                    break
                self._sleep(self._backoff(attempt))
        # bounded retries exhausted -> fall back to local, record which reasoner answered (R6.3)
        c = self._reasoner_local.complete(Role.REASONING, prompt, max_tokens=max_tokens, system=system)
        return replace(c, fell_back=True, fallback_reason=f"cloud unavailable: {last}")


# --------------------------------------------------------------------------- factory
def build_model_provider(
    engagement,
    *,
    http_post: HttpPost | None = None,
    residency: ResidencyManager | None = None,
    sleep: Callable[[float], None] | None = None,
    ollama_base_url: str | None = None,
    deepseek_base_url: str | None = None,
    deepseek_api_key: str | None = None,
    cloud_retries: int = 2,
) -> RoutedProvider:
    """Wire a RoutedProvider from an Engagement + env/defaults.

    The cloud teacher is constructed ONLY for a `practice` engagement AND only when an API key is
    available; a `real` engagement never gets one (R7.4). Secrets come from the environment
    (`DEEPSEEK_API_KEY`), never from `engagement.toml`.
    """
    residency = residency if residency is not None else ResidencyManager()
    ollama_url = ollama_base_url or os.environ.get("SALTPILOT_OLLAMA_URL") or DEFAULT_OLLAMA_URL

    analysis = OllamaProvider(
        engagement.models.analysis, base_url=ollama_url, residency=residency, http_post=http_post
    )
    reasoner_local = OllamaProvider(
        engagement.models.reasoner_local, base_url=ollama_url, residency=residency, http_post=http_post
    )

    reasoner_cloud: DeepSeekV4Provider | None = None
    if engagement.kind == "practice":
        key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
        if key:
            reasoner_cloud = DeepSeekV4Provider(
                engagement.models.reasoner_cloud,
                base_url=deepseek_base_url or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_URL,
                api_key=key,
                http_post=http_post,
            )
    # kind == 'real': reasoner_cloud stays None -> cloud is structurally unreachable (R7.4).

    return RoutedProvider(
        engagement,
        analysis=analysis,
        reasoner_local=reasoner_local,
        reasoner_cloud=reasoner_cloud,
        cloud_retries=cloud_retries,
        sleep=sleep,
    )
