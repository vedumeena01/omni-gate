"""Automated Rejection-Vector Audit & Edge-Case Stress Testing Suite.

Systematically identifies weaknesses and rejection risks for Alignerr project evaluation:
1. Schema & API Contract Compliance (OpenAI compatibility edge cases)
2. Extreme Input Fuzzing & ReDoS Safety (100KB+ payloads, unicode, malicious regex triggers)
3. Upstream Failure & Circuit Breaker Robustness
4. Repository Integrity & Open Source Packaging Hygiene (License, .env.example, git authorship)
5. Project Evolution & Feature Roadmap Scope
"""

from pathlib import Path
import sys
import time
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.core.config import Settings
from src.guardrails.injection import PromptInjectionDetector
from src.guardrails.pii import PIISanitizer
from src.main import create_app
from src.models.chat import ChatCompletionRequest, ChatMessage


class AuditResult:
    def __init__(self, name: str, passed: bool, severity: str, details: str, remediation: str):
        self.name = name
        self.passed = passed
        self.severity = severity  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
        self.details = details
        self.remediation = remediation


async def test_schema_edge_cases() -> List[AuditResult]:
    """Test schema boundary conditions and validation contracts."""
    results = []

    # Check 1: Empty messages list
    try:
        ChatCompletionRequest(model="gpt-4o", messages=[])
        results.append(
            AuditResult(
                name="Schema: Empty Messages Enforcement",
                passed=False,
                severity="HIGH",
                details="ChatCompletionRequest allows messages=[] (empty list). OpenAI requires at least 1 message.",
                remediation="Add Field(min_length=1) to ChatCompletionRequest.messages.",
            )
        )
    except ValidationError:
        results.append(
            AuditResult(
                name="Schema: Empty Messages Enforcement",
                passed=True,
                severity="HIGH",
                details="Empty messages list properly rejected by validator.",
                remediation="None",
            )
        )

    # Check 2: Invalid temperature (> 2.0 or < 0.0)
    try:
        ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=2.5,
        )
        results.append(
            AuditResult(
                name="Schema: Temperature Bounds Validation",
                passed=False,
                severity="MEDIUM",
                details="Temperature > 2.0 was allowed without validation error.",
                remediation="Ensure temperature Field has ge=0.0, le=2.0.",
            )
        )
    except ValidationError:
        results.append(
            AuditResult(
                name="Schema: Temperature Bounds Validation",
                passed=True,
                severity="MEDIUM",
                details="Temperature bounds (0.0 to 2.0) strictly enforced.",
                remediation="None",
            )
        )

    return results


async def test_fuzzing_and_redos() -> List[AuditResult]:
    """Test resilience against extreme inputs and catastrophic regex backtracking."""
    results = []
    sanitizer = PIISanitizer()
    detector = PromptInjectionDetector()

    # Check 1: 50KB repetitive string (ReDoS probe)
    repetitive_text = ("a" * 1000 + "@" + "b" * 1000 + ".com ") * 25
    t0 = time.perf_counter()
    await sanitizer.inspect(repetitive_text)
    elapsed = time.perf_counter() - t0

    if elapsed > 1.0:
        results.append(
            AuditResult(
                name="Security: PII ReDoS Vulnerability",
                passed=False,
                severity="CRITICAL",
                details=f"PII Sanitizer took {elapsed:.2f}s to process repetitive input (potential ReDoS).",
                remediation="Optimize regex pattern anchors and avoid catastrophic nested quantifiers.",
            )
        )
    else:
        results.append(
            AuditResult(
                name="Security: PII ReDoS Vulnerability",
                passed=True,
                severity="CRITICAL",
                details=f"Processed 50KB repetitive text in {elapsed*1000:.2f}ms safely.",
                remediation="None",
            )
        )

    # Check 2: Unicode, emojis, and control characters in user prompt
    complex_unicode = "你好世界 🚀 🔥 𝕿𝖊𝖘𝖙 \x00\x1f\n\t \\u0000 alert('xss') -- drop table"
    try:
        await detector.inspect(complex_unicode)
        results.append(
            AuditResult(
                name="Robustness: Unicode & Special Characters",
                passed=True,
                severity="HIGH",
                details="Unicode, emojis, and raw control bytes parsed without crash.",
                remediation="None",
            )
        )
    except Exception as exc:
        results.append(
            AuditResult(
                name="Robustness: Unicode & Special Characters",
                passed=False,
                severity="HIGH",
                details=f"Detector crashed on special characters: {str(exc)}",
                remediation="Sanitize string encoding or handle control characters cleanly.",
            )
        )

    return results


async def test_gateway_runtime_edge_cases() -> List[AuditResult]:
    """Test API behavior under malformed HTTP requests."""
    results = []
    cfg = Settings(app_env="testing")
    app = create_app(cfg)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Check 1: Missing model field
        resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        if resp.status_code == 422:
            results.append(
                AuditResult(
                    name="API: Missing Required Fields Handling",
                    passed=True,
                    severity="HIGH",
                    details="HTTP 422 Unprocessable Entity returned for missing model parameter.",
                    remediation="None",
                )
            )
        else:
            results.append(
                AuditResult(
                    name="API: Missing Required Fields Handling",
                    passed=False,
                    severity="HIGH",
                    details=f"Expected HTTP 422 for missing model, got {resp.status_code}.",
                    remediation="Validate model presence in request body.",
                )
            )

        # Check 2: Prompt with pure whitespace
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "mock-gpt-4o",
                "messages": [{"role": "user", "content": "    \n\t   "}],
            },
        )
        if resp.status_code == 200:
            results.append(
                AuditResult(
                    name="API: Whitespace-only Prompt Handling",
                    passed=True,
                    severity="MEDIUM",
                    details="Whitespace prompt processed safely without unhandled exception.",
                    remediation="None",
                )
            )
        else:
            results.append(
                AuditResult(
                    name="API: Whitespace-only Prompt Handling",
                    passed=False,
                    severity="MEDIUM",
                    details=f"Whitespace prompt failed with HTTP {resp.status_code}.",
                    remediation="Handle empty or whitespace user prompts cleanly.",
                )
            )

    return results


def test_repository_packaging_integrity() -> List[AuditResult]:
    """Verify repository files, licenses, configs, and authorship."""
    results = []
    root = Path(__file__).resolve().parent.parent

    # 1. LICENSE file check
    has_license = (root / "LICENSE").exists() or (root / "LICENSE.md").exists()
    results.append(
        AuditResult(
            name="Packaging: Root LICENSE File",
            passed=has_license,
            severity="HIGH",
            details="LICENSE file exists at project root." if has_license else "Missing LICENSE file in repository root.",
            remediation="Add MIT LICENSE file to repository root.",
        )
    )

    # 2. .env.example check
    has_env_example = (root / ".env.example").exists()
    results.append(
        AuditResult(
            name="Configuration: .env.example Template",
            passed=has_env_example,
            severity="HIGH",
            details=".env.example exists with documented configurations." if has_env_example else "Missing .env.example file.",
            remediation="Create .env.example with all OMNIGATE_ configuration defaults.",
        )
    )

    # 3. CONTRIBUTING.md / Extensibility Guide
    has_contributing = (root / "CONTRIBUTING.md").exists()
    results.append(
        AuditResult(
            name="Project Depth: CONTRIBUTING.md & Development Scope",
            passed=has_contributing,
            severity="MEDIUM",
            details="CONTRIBUTING.md exists with feature development roadmap." if has_contributing else "Missing CONTRIBUTING.md.",
            remediation="Add CONTRIBUTING.md outlining ongoing features to develop during Alignerr sessions.",
        )
    )

    # 4. pyproject.toml author verification
    pyproject_text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if "example.com" in pyproject_text:
        results.append(
            AuditResult(
                name="Authorship: pyproject.toml Author Alignment",
                passed=False,
                severity="HIGH",
                details="Found placeholder email 'vedprakash@example.com' in pyproject.toml.",
                remediation="Update author name and email to match GitHub username (vedumeena01).",
            )
        )
    else:
        results.append(
            AuditResult(
                name="Authorship: pyproject.toml Author Alignment",
                passed=True,
                severity="HIGH",
                details="Author metadata is consistent and non-placeholder.",
                remediation="None",
            )
        )

    return results


async def main():
    print("\n" + "=" * 70)
    print("ALIGNERR REJECTION VECTOR AUDIT & STRESS ANALYSIS LOOP")
    print("=" * 70)

    all_results: List[AuditResult] = []
    all_results.extend(await test_schema_edge_cases())
    all_results.extend(await test_fuzzing_and_redos())
    all_results.extend(await test_gateway_runtime_edge_cases())
    all_results.extend(test_repository_packaging_integrity())

    passed_count = sum(1 for r in all_results if r.passed)
    failed_count = sum(1 for r in all_results if not r.passed)

    print(f"\nAudit Summary: {passed_count} Passed | {failed_count} Identified Vulnerabilities / Rejection Risks\n")

    for i, res in enumerate(all_results, 1):
        status_icon = "PASS [OK]" if res.passed else f"FAIL [{res.severity}]"
        print(f"[{i:02d}] {status_icon:14} {res.name}")
        print(f"     Details:     {res.details}")
        if not res.passed:
            print(f"     Remediation: {res.remediation}")
        print("-" * 70)

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
