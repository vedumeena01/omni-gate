"""Mock LLM Provider for deterministic offline testing and benchmarking."""

import asyncio
import time
from typing import AsyncIterator, List, Optional
from src.models.chat import (
    ChatChoice,
    ChatChunkChoice,
    ChatChunkDelta,
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Usage,
)
from src.providers.base import BaseProvider


class MockProvider(BaseProvider):
    """Configurable mock provider that produces deterministic outputs without external API calls."""

    def __init__(
        self,
        provider_name: str = "mock-openai",
        default_reply: str = "This is a deterministic response from OmniGate MockProvider.",
        latency_seconds: float = 0.0,
        should_fail: bool = False,
        failure_exception: Optional[Exception] = None,
    ):
        super().__init__(provider_name=provider_name)
        self.default_reply = default_reply
        self.latency_seconds = latency_seconds
        self.should_fail = should_fail
        self.failure_exception = failure_exception or RuntimeError(
            f"Provider '{provider_name}' upstream connection error (HTTP 502)"
        )
        self.call_count = 0

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Generate response or raise configured failure."""
        self.call_count += 1
        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

        if self.should_fail:
            raise self.failure_exception

        start_time = time.perf_counter()
        last_prompt = request.get_last_user_prompt()
        content = (
            f"Echo: {last_prompt}" if last_prompt and self.default_reply == "echo" else self.default_reply
        )

        prompt_words = sum(len(m.content.split()) for m in request.messages)
        completion_words = len(content.split())
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return ChatCompletionResponse(
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=max(1, prompt_words),
                completion_tokens=max(1, completion_words),
                total_tokens=max(1, prompt_words) + max(1, completion_words),
            ),
            cached=False,
            latency_ms=round(elapsed_ms, 2),
            provider=self.provider_name,
        )

    async def generate_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Stream response chunk by chunk."""
        self.call_count += 1
        if self.should_fail:
            raise self.failure_exception

        last_prompt = request.get_last_user_prompt()
        content = (
            f"Echo: {last_prompt}" if last_prompt and self.default_reply == "echo" else self.default_reply
        )
        tokens: List[str] = content.split()

        # First chunk: role
        yield ChatCompletionChunk(
            model=request.model,
            choices=[
                ChatChunkChoice(
                    index=0,
                    delta=ChatChunkDelta(role="assistant"),
                    finish_reason=None,
                )
            ],
        )

        # Content chunks
        for i, token in enumerate(tokens):
            if self.latency_seconds > 0:
                await asyncio.sleep(self.latency_seconds / max(len(tokens), 1))
            chunk_text = token + (" " if i < len(tokens) - 1 else "")
            yield ChatCompletionChunk(
                model=request.model,
                choices=[
                    ChatChunkChoice(
                        index=0,
                        delta=ChatChunkDelta(content=chunk_text),
                        finish_reason=None,
                    )
                ],
            )

        # Final chunk
        yield ChatCompletionChunk(
            model=request.model,
            choices=[
                ChatChunkChoice(
                    index=0,
                    delta=ChatChunkDelta(),
                    finish_reason="stop",
                )
            ],
        )

    async def is_healthy(self) -> bool:
        """Check if provider is operational."""
        return not self.should_fail
