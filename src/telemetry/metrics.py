"""Structured telemetry, token accounting, and latency percentiles tracker."""

import asyncio
from typing import Any, Dict, List


class MetricsTracker:
    """Collects runtime telemetry, cache hit ratios, and latency distribution."""

    def __init__(self, max_latency_samples: int = 5000):
        self.max_latency_samples = max_latency_samples
        self._lock = asyncio.Lock()

        self.total_requests = 0
        self.successful_requests = 0
        self.rate_limited_requests = 0
        self.guardrail_blocked_requests = 0

        self.exact_cache_hits = 0
        self.semantic_cache_hits = 0
        self.cache_misses = 0

        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.cached_tokens_saved = 0

        self._latencies_ms: List[float] = []

    async def record_request(
        self,
        success: bool = True,
        latency_ms: float = 0.0,
        cache_type: str = "none",  # "none" | "exact" | "semantic"
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        rate_limited: bool = False,
        guardrail_blocked: bool = False,
    ) -> None:
        """Record telemetry attributes for a processed request."""
        async with self._lock:
            self.total_requests += 1

            if rate_limited:
                self.rate_limited_requests += 1
                return

            if guardrail_blocked:
                self.guardrail_blocked_requests += 1
                return

            if success:
                self.successful_requests += 1

            # Latency sampling
            if len(self._latencies_ms) >= self.max_latency_samples:
                self._latencies_ms.pop(0)
            self._latencies_ms.append(latency_ms)

            # Caching & Tokens
            if cache_type == "exact":
                self.exact_cache_hits += 1
                self.cached_tokens_saved += prompt_tokens + completion_tokens
            elif cache_type == "semantic":
                self.semantic_cache_hits += 1
                self.cached_tokens_saved += prompt_tokens + completion_tokens
            else:
                self.cache_misses += 1
                self.total_prompt_tokens += prompt_tokens
                self.total_completion_tokens += completion_tokens

    async def get_summary(self) -> Dict[str, Any]:
        """Compute aggregated statistics and latency percentiles."""
        async with self._lock:
            total_hits = self.exact_cache_hits + self.semantic_cache_hits
            total_cache_queries = total_hits + self.cache_misses
            hit_rate = (
                round((total_hits / total_cache_queries) * 100, 2)
                if total_cache_queries > 0
                else 0.0
            )

            p50 = 0.0
            p95 = 0.0
            p99 = 0.0
            avg_latency = 0.0

            if self._latencies_ms:
                sorted_lats = sorted(self._latencies_ms)
                n = len(sorted_lats)
                p50 = round(sorted_lats[int(n * 0.50)], 2)
                p95 = round(sorted_lats[min(int(n * 0.95), n - 1)], 2)
                p99 = round(sorted_lats[min(int(n * 0.99), n - 1)], 2)
                avg_latency = round(sum(sorted_lats) / n, 2)

            # Estimated cost savings calculation (e.g. $0.01 per 1K prompt tokens, $0.03 per 1K completion tokens)
            estimated_usd_saved = round((self.cached_tokens_saved / 1000.0) * 0.015, 4)

            return {
                "requests": {
                    "total": self.total_requests,
                    "successful": self.successful_requests,
                    "rate_limited": self.rate_limited_requests,
                    "guardrail_blocked": self.guardrail_blocked_requests,
                },
                "cache": {
                    "hit_rate_pct": hit_rate,
                    "exact_hits": self.exact_cache_hits,
                    "semantic_hits": self.semantic_cache_hits,
                    "misses": self.cache_misses,
                },
                "tokens": {
                    "prompt_tokens": self.total_prompt_tokens,
                    "completion_tokens": self.total_completion_tokens,
                    "cached_tokens_saved": self.cached_tokens_saved,
                    "estimated_usd_saved": estimated_usd_saved,
                },
                "latency_ms": {
                    "avg": avg_latency,
                    "p50": p50,
                    "p95": p95,
                    "p99": p99,
                },
            }

    async def reset(self) -> None:
        """Reset all metrics."""
        async with self._lock:
            self.total_requests = 0
            self.successful_requests = 0
            self.rate_limited_requests = 0
            self.guardrail_blocked_requests = 0
            self.exact_cache_hits = 0
            self.semantic_cache_hits = 0
            self.cache_misses = 0
            self.total_prompt_tokens = 0
            self.total_completion_tokens = 0
            self.cached_tokens_saved = 0
            self._latencies_ms.clear()
