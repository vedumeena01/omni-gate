"""Token bucket rate limiter for per-key and per-tenant request throttling."""

import asyncio
import time
from typing import Dict, Tuple


class TokenBucket:
    """Represents a token bucket for a specific rate-limiting key."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate  # Tokens added per second
        self.capacity = capacity  # Maximum bucket capacity
        self.tokens = capacity
        self.last_update = time.monotonic()

    def consume(self, tokens_requested: float = 1.0) -> Tuple[bool, float]:
        """Attempt to consume tokens. Returns (is_allowed, retry_after_seconds)."""
        now = time.monotonic()
        elapsed = now - self.last_update
        self.last_update = now

        # Replenish tokens based on elapsed time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

        if self.tokens >= tokens_requested:
            self.tokens -= tokens_requested
            return True, 0.0

        needed = tokens_requested - self.tokens
        retry_after = needed / self.rate if self.rate > 0 else 60.0
        return False, round(retry_after, 3)


class RateLimiter:
    """Manages rate limiters across different API keys or client identifiers."""

    def __init__(self, requests_per_minute: int = 60, burst_capacity: int = 10):
        self.rate = requests_per_minute / 60.0
        self.burst_capacity = float(burst_capacity)
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(
        self, key: str, tokens: float = 1.0
    ) -> Tuple[bool, float]:
        """Check if request is allowed under the key's token bucket."""
        async with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    rate=self.rate, capacity=self.burst_capacity
                )
            bucket = self._buckets[key]
            return bucket.consume(tokens)

    async def reset(self) -> None:
        """Clear all active rate limit buckets."""
        async with self._lock:
            self._buckets.clear()
