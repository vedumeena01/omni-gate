"""Circuit Breaker pattern implementation for upstream LLM resilience."""

import asyncio
from enum import Enum
import time
from typing import Optional


class CircuitState(str, Enum):
    """Possible states for the circuit breaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(Exception):
    """Raised when request is rejected because the circuit is OPEN."""

    def __init__(self, service_name: str, retry_after: float):
        super().__init__(
            f"Circuit breaker for service '{service_name}' is OPEN. Retry after {retry_after:.1f}s."
        )
        self.service_name = service_name
        self.retry_after = retry_after


class CircuitBreaker:
    """Protects against cascading failures by tripping open when failure threshold is breached."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 2,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.monotonic()
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        """Check if request execution is permitted."""
        async with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                elapsed = now - self.last_state_change
                if elapsed >= self.recovery_timeout:
                    # Transition to HALF_OPEN to test upstream recovery
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    self.failure_count = 0
                    self.last_state_change = now
                    return True
                raise CircuitBreakerOpenException(
                    service_name=self.service_name,
                    retry_after=round(self.recovery_timeout - elapsed, 2),
                )

            if self.state == CircuitState.HALF_OPEN:
                return True

            return False

    async def record_success(self) -> None:
        """Record successful upstream execution."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_state_change = time.monotonic()
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def record_failure(self) -> None:
        """Record upstream execution failure."""
        async with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.HALF_OPEN:
                # Immediate trip back to OPEN
                self.state = CircuitState.OPEN
                self.last_state_change = now
                self.failure_count = self.failure_threshold
            elif self.state == CircuitState.CLOSED:
                self.failure_count += 1
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.last_state_change = now
