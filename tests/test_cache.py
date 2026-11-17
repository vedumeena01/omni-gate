"""Tests for Two-Tier Caching System (Exact SHA-256 and Semantic Cosine Cache)."""

import asyncio
import pytest
from src.cache.exact import ExactMatchCache
from src.cache.semantic import SemanticCache
from src.models.chat import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Usage,
)


def _make_dummy_response(content: str = "Cached answer.") -> ChatCompletionResponse:
    return ChatCompletionResponse(
        model="gpt-4o",
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content=content),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )


@pytest.mark.asyncio
async def test_exact_cache_set_and_get():
    cache = ExactMatchCache(max_size=10, default_ttl_seconds=60)
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="What is quantum computing?")],
    )

    # Initially empty
    assert await cache.get(req) is None
    assert cache.misses == 1

    # Store response
    dummy_resp = _make_dummy_response("Quantum computing uses qubits.")
    await cache.set(req, dummy_resp)

    # Retrieve cached response
    hit = await cache.get(req)
    assert hit is not None
    assert hit.cached is True
    assert hit.cache_type == "exact"
    assert hit.choices[0].message.content == "Quantum computing uses qubits."
    assert cache.hits == 1


@pytest.mark.asyncio
async def test_exact_cache_ttl_expiration():
    cache = ExactMatchCache(default_ttl_seconds=1)
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Expiring test")],
    )
    await cache.set(req, _make_dummy_response(), ttl_seconds=0)
    await asyncio.sleep(0.01)

    hit = await cache.get(req)
    assert hit is None


@pytest.mark.asyncio
async def test_semantic_cache_hit_and_miss():
    cache = SemanticCache(similarity_threshold=0.85)
    req1 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(
                role="user", content="How do I calculate the area of a circle in Python?"
            )
        ],
    )
    resp = _make_dummy_response("Use math.pi * r ** 2")
    await cache.set(req1, resp)

    # Similar query (paraphrased formulation)
    req2 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(
                role="user", content="How to calculate the area of a circle in Python?"
            )
        ],
    )
    res = await cache.get(req2)
    assert res is not None
    cached_resp, score = res
    assert cached_resp.cached is True
    assert cached_resp.cache_type == "semantic"
    assert score >= 0.85
    assert cached_resp.choices[0].message.content == "Use math.pi * r ** 2"

    # Completely unrelated query
    req3 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Who won the World Cup in 1998?")],
    )
    unrelated_res = await cache.get(req3)
    assert unrelated_res is None
