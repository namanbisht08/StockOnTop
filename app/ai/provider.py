import logging
from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Raised when a provider fails to produce a usable response - network
    error, auth failure, timeout, or an empty/malformed reply. The analyzer
    catches this to fall through to the next configured provider.
    """


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return the raw text completion for the given prompt."""


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-flash-latest",
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("Gemini API key is required")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        try:
            response = httpx.post(
                url,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMProviderError(f"Gemini request failed: {e}") from e


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data["response"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise LLMProviderError(f"Ollama request failed: {e}") from e


class MockLLMProvider(LLMProvider):
    """No network, deterministic - for tests."""

    def __init__(self, response: Optional[str] = None, fail: bool = False):
        self.response = response
        self.fail = fail
        self.last_prompt: Optional[str] = None

    def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.fail:
            raise LLMProviderError("mock provider configured to fail")
        return self.response if self.response is not None else "{}"


def build_default_providers() -> List[LLMProvider]:
    """Gemini first (if configured), then Ollama as a free/local fallback.
    Neither provider is required to be reachable - CandidateAnalyzer falls
    back to a deterministic-only result if every provider fails.
    """
    settings = get_settings()
    providers: List[LLMProvider] = []

    if settings.gemini_api_key:
        providers.append(GeminiProvider(settings.gemini_api_key, settings.gemini_model))
    else:
        logger.info("GEMINI_API_KEY not set; skipping Gemini provider")

    providers.append(OllamaProvider(settings.ollama_base_url, settings.ollama_model))
    return providers
