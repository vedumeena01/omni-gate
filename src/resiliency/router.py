"""Resilient model routing with automatic fallback cascading and circuit breakers."""

import logging
from typing import AsyncIterator, Dict, List
from src.models.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from src.providers.base import BaseProvider
from src.resiliency.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
)

logger = logging.getLogger("omni_gate.router")


class AllProvidersFailedException(Exception):
    """Raised when all primary and fallback providers fail to fulfill the request."""

    def __init__(self, errors: Dict[str, str]):
        super().__init__(f"All upstream model providers failed: {errors}")
        self.errors = errors


class ResilientRouter:
    """Routes requests to primary provider with automatic circuit-breaker-backed fallback cascading."""

    def __init__(
        self,
        providers: List[BaseProvider],
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        if not providers:
            raise ValueError("ResilientRouter requires at least one provider.")
        self.providers = providers
        self.breakers: Dict[str, CircuitBreaker] = {
            p.provider_name: CircuitBreaker(
                service_name=p.provider_name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
            for p in providers
        }

    async def execute(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Attempt primary provider; on failure, cascade down fallback chain."""
        errors: Dict[str, str] = {}

        for provider in self.providers:
            name = provider.provider_name
            breaker = self.breakers[name]

            try:
                await breaker.can_execute()
                response = await provider.generate(request)
                await breaker.record_success()
                return response
            except CircuitBreakerOpenException as cbe:
                logger.warning(
                    "Skipping provider '%s' due to open circuit: %s", name, str(cbe)
                )
                errors[name] = f"Circuit OPEN (retry in {cbe.retry_after}s)"
            except Exception as exc:
                logger.error("Provider '%s' failed: %s", name, str(exc))
                await breaker.record_failure()
                errors[name] = str(exc)

        raise AllProvidersFailedException(errors=errors)

    async def execute_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Stream from first healthy provider with fallback cascade."""
        errors: Dict[str, str] = {}

        for provider in self.providers:
            name = provider.provider_name
            breaker = self.breakers[name]

            try:
                await breaker.can_execute()
                async for chunk in provider.generate_stream(request):
                    yield chunk
                await breaker.record_success()
                return
            except CircuitBreakerOpenException as cbe:
                errors[name] = f"Circuit OPEN: {str(cbe)}"
            except Exception as exc:
                await breaker.record_failure()
                errors[name] = str(exc)

        raise AllProvidersFailedException(errors=errors)
