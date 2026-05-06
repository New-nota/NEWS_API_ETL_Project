"""Mistral AI API client for summary generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from config.config import settings

logger = logging.getLogger(__name__)


class MistralClientError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MistralCompletion:
    content: dict[str, Any]
    model_name: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


_PLACEHOLDER_KEYS = {"NO", "YOUR_MISTRAL_KEY", "CHANGE_ME"}


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```json"):
        text = text[7:].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


class MistralClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = (api_key or settings.mistral_api_key).strip()
        self.api_url = api_url or settings.mistral_api_url
        self.model = model or settings.mistral_model

        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY is not configured")
        if self.api_key.upper() in _PLACEHOLDER_KEYS:
            raise ValueError("MISTRAL_API_KEY contains a placeholder value")

    def generate_summary(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> MistralCompletion:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=settings.ai_request_timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise MistralClientError("Mistral API request timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise MistralClientError("Mistral API connection failed") from exc

        if response.status_code == 429:
            raise MistralClientError("Mistral API rate limit reached")

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logger.error("Mistral API error: %s - %s", response.status_code, response.text[:300])
            raise MistralClientError(
                f"Mistral API error: {response.status_code}"
            ) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise MistralClientError("Mistral API returned invalid JSON") from exc

        choices = data.get("choices") or []
        if not choices:
            raise MistralClientError("No choices in Mistral API response")

        content = (choices[0].get("message") or {}).get("content", "")
        if not content:
            raise MistralClientError("Empty content in Mistral API response")

        try:
            parsed = json.loads(_strip_code_fence(content))
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Mistral content as JSON: %s", content[:500])
            raise MistralClientError("Failed to parse AI response as JSON") from exc

        usage = data.get("usage") or {}
        return MistralCompletion(
            content=parsed,
            model_name=data.get("model") or self.model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )


_client: MistralClient | None = None


def get_client() -> MistralClient:
    global _client
    if _client is None:
        _client = MistralClient()
    return _client


def generate_summary(system_prompt: str, user_prompt: str) -> MistralCompletion:
    return get_client().generate_summary(system_prompt, user_prompt)
