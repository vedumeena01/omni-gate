"""Tier-2 Semantic Caching with vector embedding similarity search."""

import asyncio
import hashlib
import math
import re
from typing import List, Optional, Set, Tuple
from src.models.chat import ChatCompletionRequest, ChatCompletionResponse

STOPWORDS: Set[str] = {
    "a", "about", "an", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "our",
    "please", "tell", "the", "to", "what", "which", "who", "will", "with", "would", "you"
}


class LocalFeatureEmbedder:
    """Zero-dependency local normalized character-n-gram and token feature embedder for semantic search."""

    def __init__(self, vector_dim: int = 256):
        self.vector_dim = vector_dim

    def _hash(self, token: str) -> int:
        """Deterministic integer hash across runs."""
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        return int(digest, 16) % self.vector_dim

    def embed(self, text: str) -> List[float]:
        """Convert input text into a normalized frequency feature vector with stopword dampening."""
        cleaned = re.sub(r"[^\w\s]", "", text.lower()).strip()
        tokens = cleaned.split()
        if not tokens:
            return [0.0] * self.vector_dim

        vector = [0.0] * self.vector_dim

        # Informative content tokens receive high weight; stopwords receive low weight
        for token in tokens:
            weight = 0.2 if token in STOPWORDS else 1.5
            h = self._hash(token)
            vector[h] += weight

        # Subword character tri-grams
        for i in range(len(cleaned) - 2):
            trigram = cleaned[i : i + 3]
            h = self._hash(trigram)
            vector[h] += 0.3

        # L2 Normalization
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two unit vectors."""
        if len(vec_a) != len(vec_b):
            return 0.0
        return sum(a * b for a, b in zip(vec_a, vec_b))


class SemanticCacheEntry:
    """Stores query prompt, its embedding vector, target model, and corresponding response."""

    def __init__(
        self,
        prompt: str,
        model: str,
        vector: List[float],
        response: ChatCompletionResponse,
    ):
        self.prompt = prompt
        self.model = model
        self.vector = vector
        self.response = response


class SemanticCache:
    """Caches and retrieves LLM responses based on cosine similarity of query prompts."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        max_entries: int = 5000,
        embedder: Optional[LocalFeatureEmbedder] = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self.embedder = embedder or LocalFeatureEmbedder()
        self._entries: List[SemanticCacheEntry] = []
        self._lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def get(
        self, request: ChatCompletionRequest
    ) -> Optional[Tuple[ChatCompletionResponse, float]]:
        """Find cached response if prompt similarity exceeds threshold. Returns (response, score)."""
        prompt = request.get_last_user_prompt()
        if not prompt:
            return None

        query_vec = self.embedder.embed(prompt)

        async with self._lock:
            best_entry: Optional[SemanticCacheEntry] = None
            highest_score = 0.0

            for entry in self._entries:
                if entry.model != request.model:
                    continue
                score = self.embedder.cosine_similarity(query_vec, entry.vector)
                if score > highest_score:
                    highest_score = score
                    best_entry = entry

            if best_entry and highest_score >= self.similarity_threshold:
                self.hits += 1
                cached_resp = best_entry.response.model_copy(deep=True)
                cached_resp.cached = True
                cached_resp.cache_type = "semantic"
                return cached_resp, round(highest_score, 3)

            self.misses += 1
            return None

    async def set(
        self, request: ChatCompletionRequest, response: ChatCompletionResponse
    ) -> None:
        """Store prompt and response in the semantic cache."""
        prompt = request.get_last_user_prompt()
        if not prompt:
            return

        vector = self.embedder.embed(prompt)
        async with self._lock:
            if len(self._entries) >= self.max_entries:
                self._entries.pop(0)  # Simple FIFO eviction

            self._entries.append(
                SemanticCacheEntry(
                    prompt=prompt,
                    model=request.model,
                    vector=vector,
                    response=response,
                )
            )

    async def clear(self) -> None:
        """Purge semantic cache."""
        async with self._lock:
            self._entries.clear()
            self.hits = 0
            self.misses = 0
