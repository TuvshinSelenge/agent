"""Minimal OpenAI client (JSON mode) used by the research agent.

Kept dependency-light (uses httpx, already required). Configuration via env:
    OPENAI_API_KEY   – required
    OPENAI_MODEL     – default "gpt-4o-mini"
    OPENAI_BASE_URL  – default "https://api.openai.com/v1"
"""

from __future__ import annotations

import json
import os

import httpx


class LLMNotConfiguredError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise LLMNotConfiguredError("OPENAI_API_KEY ist nicht gesetzt.")

    def complete_json(self, system: str, user: str) -> dict:
        """Return the model's JSON object response as a dict."""
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
