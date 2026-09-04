"""Minimal OpenAI client used by the research agent.

Kept dependency-light (uses httpx, already required). Configuration via env:
    OPENAI_API_KEY   – required
    OPENAI_MODEL     – default "gpt-5.6-terra"
    OPENAI_BASE_URL  – default "https://api.openai.com/v1"

Note: reasoning models (e.g. gpt-5.6-terra) reject a custom ``temperature`` and
require ``reasoning_effort: "none"`` to use function tools in chat/completions,
so we never send ``temperature`` and set ``reasoning_effort`` when tools are used.
"""

from __future__ import annotations

import json
import os

import httpx

DEFAULT_MODEL = "gpt-5.6-terra"


class LLMNotConfiguredError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self.base_url = (
            base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise LLMNotConfiguredError("OPENAI_API_KEY ist nicht gesetzt.")

    def _post(self, payload: dict) -> dict:
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, **payload},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def complete_json(self, system: str, user: str) -> dict:
        """Return the model's JSON object response as a dict (no tools)."""
        data = self._post(
            {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
            }
        )
        return json.loads(data["choices"][0]["message"]["content"])

    def chat_json(self, messages: list[dict]) -> dict:
        """Like :meth:`chat` but forces a JSON-object response and parses it."""
        data = self._post(
            {"messages": messages, "response_format": {"type": "json_object"}}
        )
        return json.loads(data["choices"][0]["message"]["content"])

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Return the raw assistant message. Enables tool calls when ``tools`` given."""
        payload: dict = {"messages": messages}
        if tools:
            # Function tools + reasoning models require reasoning_effort "none".
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["reasoning_effort"] = "none"
        data = self._post(payload)
        return data["choices"][0]["message"]
