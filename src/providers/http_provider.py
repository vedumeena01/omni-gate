"""HTTP Provider for upstream OpenAI-compatible LLM endpoints."""

import json
from typing import AsyncIterator, Optional
import httpx
from src.models.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from src.providers.base import BaseProvider


class UpstreamProviderError(Exception):
    """Exception raised when an upstream LLM API call fails."""

    def __init__(self, status_code: int, message: str, provider: str):
        super().__init__(f"Provider '{provider}' error [{status_code}]: {message}")
        self.status_code = status_code
        self.provider = provider


class HttpProvider(BaseProvider):
    """Upstream HTTP client for OpenAI-compatible LLM APIs."""

    def __init__(
        self,
        provider_name: str,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ):
        super().__init__(provider_name=provider_name)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.AsyncClient(headers=headers, timeout=self.timeout)

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Forward chat completion request to upstream endpoint."""
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        payload = request.model_dump(exclude_none=True)
        payload["stream"] = False

        try:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                raise UpstreamProviderError(
                    status_code=response.status_code,
                    message=response.text,
                    provider=self.provider_name,
                )
            data = response.json()
            res = ChatCompletionResponse.model_validate(data)
            res.provider = self.provider_name
            return res
        except httpx.RequestError as exc:
            raise UpstreamProviderError(
                status_code=503,
                message=f"Network communication failure: {str(exc)}",
                provider=self.provider_name,
            ) from exc

    async def generate_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Stream response chunks from upstream SSE endpoint."""
        client = self._get_client()
        url = f"{self.base_url}/chat/completions"
        payload = request.model_dump(exclude_none=True)
        payload["stream"] = True

        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise UpstreamProviderError(
                        status_code=response.status_code,
                        message=error_text.decode("utf-8", errors="replace"),
                        provider=self.provider_name,
                    )
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_dict = json.loads(data_str)
                            yield ChatCompletionChunk.model_validate(chunk_dict)
                        except json.JSONDecodeError:
                            continue
        except httpx.RequestError as exc:
            raise UpstreamProviderError(
                status_code=503,
                message=f"Streaming network failure: {str(exc)}",
                provider=self.provider_name,
            ) from exc

    async def is_healthy(self) -> bool:
        """Check upstream health via /models endpoint."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self.base_url}/models")
            return resp.status_code == 200
        except Exception:
            return False
