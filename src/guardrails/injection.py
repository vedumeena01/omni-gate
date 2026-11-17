"""Prompt Injection and Jailbreak detection guardrail."""

import re
from typing import List, Pattern, Tuple
from src.guardrails.base import BaseGuardrail, GuardrailResult


class PromptInjectionDetector(BaseGuardrail):
    """Detects adversarial jailbreak attempts and system instruction overrides."""

    def __init__(
        self,
        name: str = "injection_detector",
        threshold: float = 0.60,
    ):
        super().__init__(name=name)
        self.threshold = threshold

        # Heuristic rules: (name, regex pattern, weight)
        self._rules: List[Tuple[str, Pattern[str], float]] = [
            (
                "ignore_previous",
                re.compile(
                    r"\b(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|above)\s+(instructions|rules|prompts|guidelines)\b",
                    re.IGNORECASE,
                ),
                0.85,
            ),
            (
                "developer_mode",
                re.compile(
                    r"\b(developer\s+mode|dan\s+mode|jailbreak|unfiltered\s+mode|unrestricted\s+ai)\b",
                    re.IGNORECASE,
                ),
                0.80,
            ),
            (
                "system_prompt_leak",
                re.compile(
                    r"\b(repeat|print|reveal|output|display)\s+(your\s+)?(system\s+prompt|initial\s+instructions|system\s+instructions)\b",
                    re.IGNORECASE,
                ),
                0.75,
            ),
            (
                "tag_injection",
                re.compile(
                    r"(</system>|</instruction>|\[SYSTEM\]|<admin_override>)",
                    re.IGNORECASE,
                ),
                0.70,
            ),
            (
                "roleplay_bypass",
                re.compile(
                    r"\b(you\s+must\s+never\s+refuse|you\s+have\s+no\s+safety\s+guidelines|you\s+are\s+free\s+from\s+rules)\b",
                    re.IGNORECASE,
                ),
                0.75,
            ),
        ]

    async def inspect(self, text: str) -> GuardrailResult:
        """Inspect text against adversarial prompt injection heuristics."""
        matched_rules: List[str] = []
        highest_weight = 0.0

        for rule_name, pattern, weight in self._rules:
            if pattern.search(text):
                matched_rules.append(rule_name)
                highest_weight = max(highest_weight, weight)

        # Composite score calculation
        if len(matched_rules) > 1:
            confidence = min(1.0, highest_weight + 0.15 * (len(matched_rules) - 1))
        else:
            confidence = highest_weight

        is_injection = confidence >= self.threshold

        return GuardrailResult(
            passed=not is_injection,
            sanitized_text=None,
            violation_type="prompt_injection" if is_injection else None,
            confidence_score=round(confidence, 2),
            details={
                "matched_rules": matched_rules,
                "confidence": round(confidence, 2),
                "threshold": self.threshold,
            },
        )
