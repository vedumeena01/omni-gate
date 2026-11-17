# OmniGate: Production AI Gateway & Evaluation Harness
## Specification Document (.gsd/SPEC.md)

### 1. Project Overview & Alignerr Positioning
- **Project Name:** OmniGate (or `omni-gateway`)
- **Category:** Production-Grade AI Gateway, Guardrails Engine, and Evaluation Harness.
- **Language / Runtime:** Python 3.12+ (FastAPI, Asyncio, Pydantic v2).
- **Primary Goal:** Provide an ultra-fast, resilient, OpenAI-compatible proxy gateway for Large Language Models (LLMs) with built-in semantic caching, enterprise guardrails, circuit breakers, and an automated evaluation benchmark suite.
- **Why this satisfies Alignerr's "Substantial Project" criteria:**
  - Real-world enterprise problem solving (reducing LLM API latency, costs, and vulnerability risks).
  - Clean modular architecture (Separation of concerns: Gateway Core, Guardrails, Cache, Router/Fallbacks, Telemetry, Eval Suite).
  - High testability with comprehensive automated tests (unit, integration, mock providers).
  - CI/CD automation, Dockerization, typing, and zero tutorial/template code.

---

### 2. Core Architecture & System Components

```
                    ┌─────────────────────────┐
                    │      Client / App       │
                    └────────────┬────────────┘
                                 │ HTTP POST /v1/chat/completions
                                 ▼
                    ┌─────────────────────────┐
                    │    OmniGate FastAPI     │
                    │   Middleware & Tracing  │
                    └────────────┬────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Token Bucket     │  │ Guardrails       │  │ Cache Engine     │
│ Rate Limiter     │  │ - PII Masking    │  │ - Exact SHA256   │
│ & Auth Validator │  │ - Injection/Jail │  │ - Semantic Cache │
└──────────────────┘  └──────────────────┘  └─────────┬────────┘
                                                      │ Cache Hit
                                                      ├────────► [Return Response]
                                                      │ Cache Miss
                                                      ▼
                                       ┌─────────────────────────┐
                                       │ Resilient Model Router  │
                                       │ - Circuit Breaker       │
                                       │ - Fallback Cascade      │
                                       │ - Retries with Jitter   │
                                       └────────────┬────────────┘
                                                    │
                             ┌──────────────────────┴──────────────────────┐
                             ▼                                             ▼
                   ┌──────────────────┐                          ┌──────────────────┐
                   │  Primary Provider│                          │ Fallback Provider│
                   │ (OpenAI/Anthropic)                          │ (Gemini/Local)   │
                   └──────────────────┘                          └──────────────────┘
                                                    │
                                                    ▼
                                       ┌─────────────────────────┐
                                       │ Observability & Eval    │
                                       │ - Token/Cost Counter    │
                                       │ - Latency Percentiles   │
                                       │ - Structured Audit Logs │
                                       └─────────────────────────┘
```

---

### 3. Key Feature Specifications

#### A. Gateway Core & API Compatibility
- Fully compliant with OpenAI chat completions schema (`/v1/chat/completions`).
- Both streaming (`text/event-stream` SSE) and non-streaming responses supported.
- Dynamic provider abstraction: Supports OpenAI, Anthropic, Gemini, and Mock Provider (for offline development and testing).

#### B. Pluggable Guardrails Engine
- **PII Detector & Sanitizer:** Regex + token-level patterns to detect and mask SSN, email, credit card numbers, and phone numbers before forwarding to upstream LLMs.
- **Prompt Injection & Jailbreak Detector:** Heuristic entropy checks, instruction-override pattern matching, and canary token validation.
- **Configurable policies:** Strict block, sanitize/redact, or audit-only mode.

#### C. Two-Tier Caching Engine
- **Tier 1 (Exact Match):** SHA-256 hash of normalized messages, model, and generation parameters. Instant sub-millisecond retrieval.
- **Tier 2 (Semantic Cache):** Cosine similarity thresholding on prompt embeddings (using local lightweight embeddings or cosine math on feature vectors) to serve cached responses for semantically equivalent queries.

#### D. Resiliency & Reliability Engine
- **Circuit Breaker:** Tracks consecutive upstream failures. State transitions: `CLOSED` (normal) -> `OPEN` (fail fast to avoid hammering failing provider) -> `HALF-OPEN` (canary probe request).
- **Fallback Cascading:** If primary provider fails or trips circuit breaker, dynamically cascades to secondary fallback model.
- **Token Bucket Rate Limiter:** Per-tenant and per-key rate limiting with sliding window tracking.

#### E. Observability & Telemetry
- Structured JSON logging with unified `X-Request-ID`.
- Accurate token accounting (prompt tokens, completion tokens, estimated cost savings from cache hits).
- Latency breakdown: Guardrail check time, cache lookup time, provider round-trip time.

#### F. Automated Evaluation Harness (`eval/`)
- Benchmark harness to evaluate:
  - Cache hit precision & false-positive rates.
  - Guardrail detection accuracy on known jailbreak benchmarks (e.g., prompt injection datasets).
  - Gateway latency overhead (ensuring gateway adds < 5ms for exact cache hit and minimal overhead on proxying).

---

### 4. Technical Stack & Dependencies
- **Core:** `fastapi`, `uvicorn`, `pydantic>=2.0`, `httpx`
- **Testing:** `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (for mocking HTTP client)
- **Typing & Linting:** `mypy`, `ruff`
- **Optional/Dev:** `rich` (for CLI & terminal dashboards)

---

### 5. Verification & CodeRabbit Gate Requirements
- `pytest -v --cov=src` must achieve > 85% branch and statement coverage.
- Zero mock shortcuts in core business logic (clean decoupled dependency injection).
- Offline capability: All test suites run completely offline without requiring real API keys (via Mock Provider & Respx fixtures).
- Documentation: Complete `README.md` with architecture diagram, installation, benchmarking guide, and API curl examples.
