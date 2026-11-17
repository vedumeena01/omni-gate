"""Abstract Base Provider interface for LLM backends."""

from abc import ABC, abstractmethod
from typing import AsyncIterator
from src.models.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)


class BaseProvider(ABC):
    """Abstract interface that all upstream model providers must implement."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    @abstractmethod
    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute a non-streaming chat completion."""
        pass

    @abstractmethod
    async def generate_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Stream chat completion chunks asynchronously."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check provider operational status."""
        pass
