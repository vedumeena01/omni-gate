"""Tests for MetricsTracker telemetry accounting."""

import pytest
from src.telemetry.metrics import MetricsTracker


@pytest.mark.asyncio
async def test_metrics_tracker_full_cycle():
    tracker = MetricsTracker()

    # Record normal miss
    await tracker.record_request(
        success=True,
        latency_ms=120.0,
        cache_type="none",
        prompt_tokens=10,
        completion_tokens=20,
    )

    # Record exact hit
    await tracker.record_request(
        success=True,
        latency_ms=2.5,
        cache_type="exact",
        prompt_tokens=10,
        completion_tokens=20,
    )

    # Record semantic hit
    await tracker.record_request(
        success=True,
        latency_ms=4.0,
        cache_type="semantic",
        prompt_tokens=10,
        completion_tokens=20,
    )

    # Record rate limited & guardrail blocked
    await tracker.record_request(rate_limited=True)
    await tracker.record_request(guardrail_blocked=True)

    summary = await tracker.get_summary()
    assert summary["requests"]["total"] == 5
    assert summary["requests"]["rate_limited"] == 1
    assert summary["requests"]["guardrail_blocked"] == 1
    assert summary["cache"]["exact_hits"] == 1
    assert summary["cache"]["semantic_hits"] == 1
    assert summary["cache"]["hit_rate_pct"] == 66.67
    assert summary["tokens"]["cached_tokens_saved"] == 60
    assert summary["latency_ms"]["avg"] > 0

    # Reset
    await tracker.reset()
    clean_summary = await tracker.get_summary()
    assert clean_summary["requests"]["total"] == 0
