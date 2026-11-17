"""Unit tests for Chat data models and cache key generation."""

from src.models.chat import (
    ChatMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatChoice,
    Usage,
)


def test_chat_message_creation():
    msg = ChatMessage(role="user", content="Hello, world!")
    assert msg.role == "user"
    assert msg.content == "Hello, world!"


def test_get_last_user_prompt():
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[
            ChatMessage(role="system", content="You are a helper."),
            ChatMessage(role="user", content="First question"),
            ChatMessage(role="assistant", content="First answer"),
            ChatMessage(role="user", content="Latest question"),
        ],
    )
    assert req.get_last_user_prompt() == "Latest question"


def test_exact_cache_key_determinism():
    req1 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Summarize this text.")],
        temperature=0.7,
    )
    req2 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Summarize this text.")],
        temperature=0.7,
    )
    req3 = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Summarize that text.")],
        temperature=0.7,
    )

    assert req1.get_exact_cache_key() == req2.get_exact_cache_key()
    assert req1.get_exact_cache_key() != req3.get_exact_cache_key()


def test_response_instantiation():
    resp = ChatCompletionResponse(
        model="gpt-4o",
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content="Generated output."),
            )
        ],
        usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )
    assert resp.id.startswith("chatcmpl-")
    assert resp.usage.total_tokens == 30
    assert resp.cached is False
