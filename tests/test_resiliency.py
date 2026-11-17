"""Tests for rate limiting, circuit breaking, and resilient router cascading."""

import asyncio
import pytest
from src.models.chat import ChatCompletionRequest, ChatMessage
from src.providers.mock import MockProvider
from src.resiliency.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
)
from src.resiliency.rate_limiter import RateLimiter
from src.resiliency.router import AllProvidersFailedException, ResilientRouter


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    limiter = RateLimiter(requests_per_minute=60, burst_capacity=2)
    # Burst 2 allowed immediately
    allowed1, _ = await limiter.check_rate_limit("user-1", tokens=1.0)
    allowed2, _ = await limiter.check_rate_limit("user-1", tokens=1.0)
    # 3rd should be rejected
    allowed3, retry_after = await limiter.check_rate_limit("user-1", tokens=1.0)

    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is False
    assert retry_after > 0.0


@pytest.mark.asyncio
async def test_circuit_breaker_trip_and_recover():
    cb = CircuitBreaker(
        service_name="test-service",
        failure_threshold=2,
        recovery_timeout=0.1,  # 100ms for fast testing
        half_open_success_threshold=1,
    )

    # Initial state CLOSED
    assert await cb.can_execute() is True

    # 1st failure
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    # 2nd failure -> Trips to OPEN
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # In OPEN state, can_execute raises CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        await cb.can_execute()

    # Wait for recovery timeout
    await asyncio.sleep(0.12)

    # Now should transition to HALF_OPEN
    assert await cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Record success in HALF_OPEN -> transitions back to CLOSED
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_resilient_router_fallback():
    primary_failing = MockProvider(
        provider_name="primary-failing",
        should_fail=True,
    )
    fallback_healthy = MockProvider(
        provider_name="fallback-healthy",
        default_reply="Hello from resilient fallback!",
    )

    router = ResilientRouter(
        providers=[primary_failing, fallback_healthy],
        failure_threshold=2,
    )

    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Ping")],
    )

    # Router should fail on primary and automatically succeed on fallback
    resp = await router.execute(req)
    assert resp.provider == "fallback-healthy"
    assert resp.choices[0].message.content == "Hello from resilient fallback!"


@pytest.mark.asyncio
async def test_resilient_router_all_fail():
    p1 = MockProvider(provider_name="p1", should_fail=True)
    p2 = MockProvider(provider_name="p2", should_fail=True)

    router = ResilientRouter(providers=[p1, p2])
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Ping")],
    )

    with pytest.raises(AllProvidersFailedException) as exc_info:
        await router.execute(req)
    assert "p1" in exc_info.value.errors
    assert "p2" in exc_info.value.errors
