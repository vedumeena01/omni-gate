"""OpenAI-compatible Chat Completion data models and schemas."""

import hashlib
import json
import time
import uuid
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single chat message in a conversation."""

    role: Literal["system", "developer", "user", "assistant", "tool", "function"]
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """Request payload for /v1/chat/completions."""

    model: str
    messages: List[ChatMessage] = Field(min_length=1, description="List of messages comprising the conversation.")
    temperature: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    n: Optional[int] = Field(default=1, ge=1)
    stream: bool = False
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stop: Optional[Union[str, List[str]]] = None
    user: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_last_user_prompt(self) -> str:
        """Extract the most recent user prompt message text."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return ""

    def get_exact_cache_key(self) -> str:
        """Compute deterministic SHA-256 fingerprint for exact match caching."""
        temp_val = 1.0 if self.temperature is None else self.temperature
        topp_val = 1.0 if self.top_p is None else self.top_p
        normalized = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
            "temperature": round(temp_val, 3),
            "top_p": round(topp_val, 3),
            "max_tokens": self.max_tokens,
            "stop": self.stop,
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class Usage(BaseModel):
    """Token usage breakdown."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatChoice(BaseModel):
    """A single completion candidate choice."""

    index: int
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    """Response payload for /v1/chat/completions."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChoice]
    usage: Usage = Field(default_factory=Usage)
    cached: bool = False
    cache_type: Optional[Literal["exact", "semantic"]] = None
    latency_ms: Optional[float] = None
    provider: Optional[str] = None


class ChatChunkDelta(BaseModel):
    """Delta payload for streaming SSE responses."""

    role: Optional[str] = None
    content: Optional[str] = None


class ChatChunkChoice(BaseModel):
    """A streaming chunk choice."""

    index: int
    delta: ChatChunkDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    """Chunk sent over SSE during streaming."""

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChunkChoice]
