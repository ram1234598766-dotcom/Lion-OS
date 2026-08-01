"""AI provider backends for the Lion-OS assistant.

Supports three OpenAI-compatible backends so the assistant works both fully
local (Ollama) and with hosted models (OpenAI, DeepSeek):

    * ``ollama``   — http://localhost:11434/v1  (default, private)
    * ``openai``   — https://api.openai.com/v1  (needs OPENAI_API_KEY)
    * ``deepseek`` — https://api.deepseek.com/v1 (needs DEEPSEEK_API_KEY)

API keys are read from environment variables and may also be stored in the
Lion-OS config (``~/.lionos/config.json``). No keys are hardcoded.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests

DEFAULT_ENDPOINTS = {
    "ollama": "http://localhost:11434/v1",
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

DEFAULT_MODELS = {
    "ollama": "llama3",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
}

ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "ollama": None,
}


class AIDisabled(Exception):
    """Raised when the AI assistant is turned off in Settings."""


class AIProvider:
    def __init__(self, provider: str, model: str, endpoint: str, api_key: str = ""):
        self.provider = provider
        self.model = model or DEFAULT_MODELS.get(provider, "")
        self.endpoint = endpoint or DEFAULT_ENDPOINTS.get(provider, "")
        self.api_key = api_key or os.environ.get(ENV_KEYS.get(provider, ""), "")
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _url(self):
        return self.endpoint.rstrip("/") + "/chat/completions"

    def chat(self, messages: List[Dict[str, str]],
             max_tokens: int = 800, temperature: float = 0.7) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        resp = self.session.post(self._url(), json=payload, timeout=90)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:200])
            except Exception:
                detail = resp.text[:200]
            raise RuntimeError(f"{self.provider} error {resp.status_code}: {detail}")
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def available(self) -> bool:
        """Cheap reachability probe: does the endpoint answer on /models?"""
        try:
            r = self.session.get(self.endpoint.rstrip("/") + "/models", timeout=4)
            return r.status_code == 200
        except Exception:
            return False

    def info(self) -> str:
        return f"{self.provider} · {self.model}"


def get_provider(config) -> Optional[AIProvider]:
    """Build a provider from a LionConfig. Returns None if AI disabled."""
    if not getattr(config, "ai_enabled", True):
        raise AIDisabled("AI assistant is disabled in Settings")
    return AIProvider(
        provider=getattr(config, "ai_provider", "ollama"),
        model=getattr(config, "ai_model", ""),
        endpoint=getattr(config, "ai_endpoint", ""),
        api_key=getattr(config, "ai_api_key", ""),
    )
