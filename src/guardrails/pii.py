"""PII (Personally Identifiable Information) detector and redaction sanitizer."""

import re
from typing import Dict, List, Pattern, Tuple
from src.guardrails.base import BaseGuardrail, GuardrailResult


class PIISanitizer(BaseGuardrail):
    """Detects and redacts sensitive PII entities before prompt forwarding."""

    def __init__(self, name: str = "pii_sanitizer"):
        super().__init__(name=name)

        # Regex patterns for high-risk PII
        self._patterns: List[Tuple[str, Pattern[str], str]] = [
            (
                "email",
                re.compile(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                    re.IGNORECASE,
                ),
                "[REDACTED_EMAIL]",
            ),
            (
                "ssn",
                re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
                "[REDACTED_SSN]",
            ),
            (
                "credit_card",
                re.compile(
                    r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b"
                ),
                "[REDACTED_CREDIT_CARD]",
            ),
            (
                "phone",
                re.compile(
                    r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b"
                ),
                "[REDACTED_PHONE]",
            ),
        ]

    async def inspect(self, text: str) -> GuardrailResult:
        """Scan text and replace detected PII with redaction tokens."""
        sanitized = text
        detected: Dict[str, int] = {}

        for pii_type, pattern, replacement in self._patterns:
            matches = pattern.findall(sanitized)
            if matches:
                detected[pii_type] = len(matches)
                sanitized = pattern.sub(replacement, sanitized)

        has_pii = bool(detected)
        return GuardrailResult(
            passed=True,  # Sanitizer modifies text without necessarily blocking
            sanitized_text=sanitized if has_pii else text,
            violation_type="pii_detected" if has_pii else None,
            confidence_score=0.95 if has_pii else 0.0,
            details={"redacted_counts": detected, "total_redactions": sum(detected.values())},
        )
