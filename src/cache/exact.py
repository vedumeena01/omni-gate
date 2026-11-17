"""Tier-1 Exact Match Caching with SHA-256 fingerprinting and TTL eviction."""

import asyncio
from collections import OrderedDict
import time
from typing import Optional
from src.models.chat import ChatCompletionRequest, ChatCompletionResponse


class ExactCacheEntry:
    """Internal cache entry wrapper storing payload and expiration time."""

    def __init__(self, response: ChatCompletionResponse, ttl_seconds: int):
        self.response = response
        self.expires_at = time.monotonic() + ttl_seconds

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.monotonic() >= self.expires_at


class ExactMatchCache:
    """High-speed in-memory LRU exact match cache."""

    def __init__(self, max_size: int = 10000, default_ttl_seconds: int = 3600):
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        self._cache: OrderedDict[str, ExactCacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(
        self, request: ChatCompletionRequest
    ) -> Optional[ChatCompletionResponse]:
        """Lookup cached response using deterministic request hash."""
        key = request.get_exact_cache_key()
        async with self._lock:
            if key not in self._cache:
                self.misses += 1
                return None

            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                self.misses += 1
                return None

            # Move to end for LRU freshness
            self._cache.move_to_end(key)
            self.hits += 1

            # Clone response and mark as cached
            cached_resp = entry.response.model_copy(deep=True)
            cached_resp.cached = True
            cached_resp.cache_type = "exact"
            return cached_resp

    async def set(
        self,
        request: ChatCompletionRequest,
        response: ChatCompletionResponse,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store response in cache."""
        key = request.get_exact_cache_key()
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self.max_size:
                # Evict oldest entry
                self._cache.popitem(last=False)

            self._cache[key] = ExactCacheEntry(response=response, ttl_seconds=ttl)

    async def clear(self) -> None:
        """Purge cache."""
        async with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0
