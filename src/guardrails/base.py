"""Base interface and result models for OmniGate Guardrails."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GuardrailResult(BaseModel):
    """Result returned by a guardrail inspection."""

    passed: bool
    sanitized_text: Optional[str] = None
    violation_type: Optional[str] = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)


class GuardrailViolationException(Exception):
    """Raised when a prompt violates a blocking guardrail policy."""

    def __init__(self, violation_type: str, details: Dict[str, Any]):
        super().__init__(f"Guardrail policy violation: {violation_type} ({details})")
        self.violation_type = violation_type
        self.details = details


class BaseGuardrail(ABC):
    """Abstract base class for all guardrail detectors and sanitizers."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def inspect(self, text: str) -> GuardrailResult:
        """Inspect and optionally sanitize input text."""
        pass


class GuardrailPipeline:
    """Orchestrates sequential execution of multiple guardrails."""

    def __init__(
        self,
        guardrails: Optional[List[BaseGuardrail]] = None,
        block_on_violation: bool = True,
    ):
        self.guardrails: List[BaseGuardrail] = guardrails or []
        self.block_on_violation = block_on_violation

    def add_guardrail(self, guardrail: BaseGuardrail) -> None:
        """Register a new guardrail into the pipeline."""
        self.guardrails.append(guardrail)

    async def execute(self, text: str) -> str:
        """Run all guardrails sequentially on the text and return sanitized version."""
        current_text = text

        for guard in self.guardrails:
            result = await guard.inspect(current_text)
            if not result.passed:
                if self.block_on_violation:
                    raise GuardrailViolationException(
                        violation_type=result.violation_type or guard.name,
                        details=result.details,
                    )
            if result.sanitized_text is not None:
                current_text = result.sanitized_text

        return current_text
