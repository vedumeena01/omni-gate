"""Tests for LLM providers (MockProvider and HttpProvider)."""

import pytest
import respx
import httpx
from src.models.chat import (
    ChatMessage,
    ChatCompletionRequest,
)
from src.providers.mock import MockProvider
from src.providers.http_provider import HttpProvider, UpstreamProviderError


@pytest.mark.asyncio
async def test_mock_provider_generate():
    provider = MockProvider(default_reply="Hello from Mock!")
    req = ChatCompletionRequest(
        model="mock-gpt-4o",
        messages=[ChatMessage(role="user", content="Ping")],
    )
    resp = await provider.generate(req)
    assert resp.model == "mock-gpt-4o"
    assert resp.choices[0].message.content == "Hello from Mock!"
    assert resp.usage.total_tokens > 0
    assert resp.provider == "mock-openai"
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_mock_provider_stream():
    provider = MockProvider(default_reply="One two three")
    req = ChatCompletionRequest(
        model="mock-gpt-4o",
        messages=[ChatMessage(role="user", content="Ping")],
        stream=True,
    )
    chunks = []
    async for chunk in provider.generate_stream(req):
        chunks.append(chunk)

    assert len(chunks) >= 3
    # Check that tokens reconstruct the message
    content_chunks = [
        c.choices[0].delta.content for c in chunks if c.choices[0].delta.content
    ]
    reconstructed = "".join(content_chunks).strip()
    assert reconstructed == "One two three"


@pytest.mark.asyncio
async def test_mock_provider_failure():
    provider = MockProvider(should_fail=True)
    req = ChatCompletionRequest(
        model="mock-gpt-4o",
        messages=[ChatMessage(role="user", content="Ping")],
    )
    with pytest.raises(RuntimeError):
        await provider.generate(req)


@pytest.mark.asyncio
@respx.mock
async def test_http_provider_generate():
    upstream_url = "https://mock.openai.com/v1"
    respx.post(f"{upstream_url}/chat/completions").respond(
        status_code=200,
        json={
            "id": "chatcmpl-upstream123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Real upstream reply."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        },
    )

    async with httpx.AsyncClient() as client:
        provider = HttpProvider(
            provider_name="openai-primary",
            base_url=upstream_url,
            api_key="sk-test",
            client=client,
        )
        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Test prompt")],
        )
        resp = await provider.generate(req)
        assert resp.id == "chatcmpl-upstream123"
        assert resp.choices[0].message.content == "Real upstream reply."
        assert resp.provider == "openai-primary"


@pytest.mark.asyncio
@respx.mock
async def test_http_provider_error_handling():
    upstream_url = "https://mock.openai.com/v1"
    respx.post(f"{upstream_url}/chat/completions").respond(
        status_code=502, text="Bad Gateway"
    )

    async with httpx.AsyncClient() as client:
        provider = HttpProvider(
            provider_name="openai-primary",
            base_url=upstream_url,
            api_key="sk-test",
            client=client,
        )
        req = ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Test prompt")],
        )
        with pytest.raises(UpstreamProviderError) as exc_info:
            await provider.generate(req)
        assert exc_info.value.status_code == 502
