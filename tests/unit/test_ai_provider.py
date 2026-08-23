import httpx
import pytest

from app.ai import provider as provider_module
from app.ai.provider import (
    GeminiProvider,
    LLMProviderError,
    MockLLMProvider,
    OllamaProvider,
    build_default_providers,
)
from app.core.config import Settings


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("POST", "http://x"), response=self
            )

    def json(self):
        return self._json_data


def test_gemini_provider_extracts_text(monkeypatch):
    def fake_post(url, params=None, json=None, timeout=None):
        assert params["key"] == "test-key"
        return _FakeResponse(
            {"candidates": [{"content": {"parts": [{"text": '{"summary": "ok"}'}]}}]}
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = GeminiProvider(api_key="test-key", model="gemini-test")

    assert provider.complete("prompt") == '{"summary": "ok"}'


def test_gemini_provider_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse({}, status_code=500)
    )
    provider = GeminiProvider(api_key="test-key")

    with pytest.raises(LLMProviderError):
        provider.complete("prompt")


def test_gemini_provider_raises_on_malformed_response(monkeypatch):
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: _FakeResponse({"unexpected": "shape"})
    )
    provider = GeminiProvider(api_key="test-key")

    with pytest.raises(LLMProviderError):
        provider.complete("prompt")


def test_gemini_provider_requires_api_key():
    with pytest.raises(ValueError):
        GeminiProvider(api_key="")


def test_ollama_provider_extracts_text(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        assert url == "http://localhost:11434/api/generate"
        assert json["model"] == "qwen2.5:7b"
        return _FakeResponse({"response": '{"summary": "ok"}'})

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5:7b")

    assert provider.complete("prompt") == '{"summary": "ok"}'


def test_ollama_provider_raises_on_connection_error(monkeypatch):
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5:7b")

    with pytest.raises(LLMProviderError):
        provider.complete("prompt")


def test_mock_llm_provider_returns_configured_response():
    provider = MockLLMProvider(response='{"summary": "hi"}')
    assert provider.complete("some prompt") == '{"summary": "hi"}'
    assert provider.last_prompt == "some prompt"


def test_mock_llm_provider_can_fail():
    provider = MockLLMProvider(fail=True)
    with pytest.raises(LLMProviderError):
        provider.complete("prompt")


def test_build_default_providers_puts_gemini_first_when_configured(monkeypatch):
    monkeypatch.setattr(
        provider_module,
        "get_settings",
        lambda: Settings(gemini_api_key="test-key", gemini_model="gemini-test"),
    )

    providers = build_default_providers()

    assert isinstance(providers[0], GeminiProvider)
    assert isinstance(providers[1], OllamaProvider)
    assert len(providers) == 2


def test_build_default_providers_falls_back_to_ollama_only_without_gemini_key(
    monkeypatch,
):
    monkeypatch.setattr(
        provider_module, "get_settings", lambda: Settings(gemini_api_key=None)
    )

    providers = build_default_providers()

    assert len(providers) == 1
    assert isinstance(providers[0], OllamaProvider)
