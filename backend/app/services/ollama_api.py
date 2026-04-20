from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings


class OllamaAPIError(RuntimeError):
    pass


class OllamaAPIClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.ollama_enabled and self.settings.ollama_model and self.settings.ollama_base_url)

    async def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise OllamaAPIError("Ollama is not configured.")

        payload = {
            "model": model,
            "stream": False,
            "format": schema,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.ollama_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                    json=payload,
                )
                if response.status_code >= 400:
                    raise OllamaAPIError(_error_message("chat_json", response))
                body = response.json()
        except httpx.TimeoutException as exc:
            raise OllamaAPIError("Ollama chat_json timed out.") from exc
        except httpx.RequestError as exc:
            raise OllamaAPIError(f"Ollama chat_json request failed: {exc}") from exc

        content = ((body.get("message") or {}).get("content") or "{}").strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaAPIError(f"Ollama returned non-JSON content: {content[:500]}") from exc


def _error_message(operation: str, response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = {"error": response.text[:500]}
    message = ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, str):
            message = error
        elif isinstance(error, dict):
            message = str(error.get("message") or "")
    if not message:
        message = response.text[:500]
    return f"Ollama {operation} failed ({response.status_code}): {message.strip()}"
