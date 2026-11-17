"""Empirical tests verifying bug fixes in OmniGate."""

import pytest
from httpx import ASGITransport, AsyncClient
from src.cache.semantic import SemanticCache
from src.core.config import Settings
from src.main import create_app
from src.models.chat import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from src.providers.http_provider import HttpProvider
from src.telemetry.metrics import MetricsTracker


@pytest.mark.asyncio
async def test_bug_temperature_zero_distinct_cache_key():
    """Bug 2: temperature=0.0 must not produce identical hash as temperature=1.0."""
    req_temp_0 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Sort this list")],
        temperature=0.0,
    )
    req_temp_1 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Sort this list")],
        temperature=1.0,
    )
    assert req_temp_0.get_exact_cache_key() != req_temp_1.get_exact_cache_key(), (
        "Cache key collision between temperature 0.0 and 1.0!"
    )


@pytest.mark.asyncio
async def test_bug_semantic_cache_model_isolation():
    """Bug 1: SemanticCache must isolate cache entries by model."""
    cache = SemanticCache(similarity_threshold=0.85)

    req_gpt4 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="What is the speed of light?")],
    )
    resp_gpt4 = ChatCompletionResponse(
        model="gpt-4o",
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content="Answer from GPT-4o"),
            )
        ],
    )
    await cache.set(req_gpt4, resp_gpt4)

    # Different model, same prompt
    req_claude = ChatCompletionRequest(
        model="claude-3-opus",
        messages=[ChatMessage(role="user", content="What is the speed of light?")],
    )
    hit = await cache.get(req_claude)

    # Must be None! Cannot leak gpt-4o response to claude-3-opus
    assert hit is None, f"Cross-model cache pollution! Leaked response from model: {hit[0].model if hit else None}"


@pytest.mark.asyncio
async def test_bug_metrics_latency_not_polluted_by_zero():
    """Bug 6: Failed requests with default 0.0 latency must not skew percentiles."""
    tracker = MetricsTracker()

    # Normal requests at 100ms
    await tracker.record_request(success=True, latency_ms=100.0)
    await tracker.record_request(success=True, latency_ms=100.0)

    # Failed request with 0.0 latency
    await tracker.record_request(success=False)

    summary = await tracker.get_summary()
    assert summary["latency_ms"]["avg"] == 100.0


@pytest.mark.asyncio
async def test_bug_streaming_telemetry_recorded():
    """Bug 4: Streaming requests must be accounted for in telemetry."""
    cfg = Settings(app_env="testing")
    app = create_app(cfg)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Initial telemetry
        r_init = await client.get("/metrics")
        init_total = r_init.json()["requests"]["total"]

        # Streaming request
        payload = {
            "model": "mock-gpt-4o",
            "messages": [{"role": "user", "content": "Count to three"}],
            "stream": True,
        }
        resp = await client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 200

        # Post-streaming telemetry must increment total requests
        r_post = await client.get("/metrics")
        post_total = r_post.json()["requests"]["total"]
        assert post_total == init_total + 1


@pytest.mark.asyncio
async def test_bug_http_provider_client_lifecycle():
    """Bug 3: HttpProvider must reuse client and close it cleanly."""
    provider = HttpProvider(
        provider_name="test-provider",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
    )
    client1 = provider._get_client()
    client2 = provider._get_client()
    assert client1 is client2  # Must reuse same persistent client instance

    await provider.aclose()
    assert provider._client is None
