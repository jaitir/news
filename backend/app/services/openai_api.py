from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings


class OpenAIAPIError(RuntimeError):
    pass


class OpenAIAPIClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.openai_api_key)

    async def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.openai_base_url}/chat/completions",
                headers=self._headers,
                json=payload,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("chat_json", response))
            body = response.json()

        message = ((body.get("choices") or [{}])[0].get("message") or {})
        content = message.get("content") or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAIAPIError(f"chat_json returned non-JSON content: {content[:500]}") from exc

    async def create_response(
        self,
        *,
        model: str,
        input_text: str,
        instructions: str | None = None,
        background: bool = False,
        reasoning: dict[str, Any] | None = None,
        max_tool_calls: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")

        payload: dict[str, Any] = {
            "model": model,
            "input": input_text,
            "background": background,
            "store": True,
        }
        if instructions:
            payload["instructions"] = instructions
        if reasoning:
            payload["reasoning"] = reasoning
        if max_tool_calls is not None:
            payload["max_tool_calls"] = max_tool_calls
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if include:
            payload["include"] = include

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.openai_base_url}/responses",
                headers=self._headers,
                json=payload,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("create_response", response))
            return response.json()

    async def retrieve_response(
        self,
        *,
        response_id: str,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")

        params = None
        if include:
            params = [("include[]", item) for item in include]

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.settings.openai_base_url}/responses/{response_id}",
                headers=self._headers,
                params=params,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("retrieve_response", response))
            return response.json()

    async def create_embeddings(
        self,
        *,
        model: str,
        inputs: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")
        if not inputs:
            return []

        payload: dict[str, Any] = {
            "model": model,
            "input": inputs,
            "encoding_format": "float",
        }
        if dimensions:
            payload["dimensions"] = dimensions

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.openai_base_url}/embeddings",
                headers=self._headers,
                json=payload,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("create_embeddings", response))
            body = response.json()

        rows = sorted(body.get("data", []), key=lambda row: row.get("index", 0))
        return [row.get("embedding", []) for row in rows]

    async def upload_batch_file(self, content: bytes, filename: str) -> dict[str, Any]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")

        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}"}
        files = {"file": (filename, content, "application/jsonl")}
        data = {"purpose": "batch"}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.settings.openai_base_url}/files",
                headers=headers,
                data=data,
                files=files,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("upload_batch_file", response))
            return response.json()

    async def create_batch(self, *, input_file_id: str, endpoint: str = "/v1/chat/completions") -> dict[str, Any]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")

        payload = {
            "input_file_id": input_file_id,
            "endpoint": endpoint,
            "completion_window": "24h",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.openai_base_url}/batches",
                headers=self._headers,
                json=payload,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("create_batch", response))
            return response.json()

    async def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.settings.openai_base_url}/batches/{batch_id}",
                headers=self._headers,
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("retrieve_batch", response))
            return response.json()

    async def download_file_text(self, file_id: str) -> str:
        if not self.is_configured:
            raise OpenAIAPIError("OPENAI_API_KEY is not configured.")
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(
                f"{self.settings.openai_base_url}/files/{file_id}/content",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            )
            if response.status_code >= 400:
                raise OpenAIAPIError(_error_message("download_file_text", response))
            return response.text


def _error_message(operation: str, response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = {"error": {"message": response.text[:500]}}
    message = ((body.get("error") or {}).get("message") or response.text[:500]).strip()
    return f"OpenAI {operation} failed ({response.status_code}): {message}"
