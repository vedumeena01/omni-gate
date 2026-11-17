# Contributing to OmniGate

Thank you for your interest in developing and extending OmniGate! This guide outlines the project structure, design philosophy, testing standards, and the active development roadmap for ongoing work.

---

## Architecture Philosophy

1. **Clean Decoupling:** Core gateway routing, caching engines, guardrail filters, and upstream providers are strictly decoupled through abstract interfaces (`BaseProvider`, `BaseGuardrail`).
2. **Defensive Programming:** Zero unhandled crashes on malformed, oversized, or adversarial inputs. Every upstream error is translated to standard OpenAI JSON responses.
3. **High Empirical Coverage:** All pull requests must maintain > 85% branch and statement test coverage (`pytest --cov=src`).
4. **Offline Development:** The project includes a high-speed `MockProvider` so core gateway features and benchmarks can be authored and tested completely offline without external API keys or cloud spend.

---

## Local Development Workflow

```bash
# 1. Clone & activate virtual environment
git clone https://github.com/vedumeena01/omni-gate.git
cd omni-gate
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate

# 2. Install editable package with dev dependencies
pip install -e .[dev]

# 3. Copy environment configuration
cp .env.example .env

# 4. Run tests and linting
ruff check .
pytest -v --cov=src --cov-report=term-missing

# 5. Run the evaluation & benchmarking suite
python eval/run_benchmarks.py
```

---

## Active Development Backlog (Upcoming Sessions)

These feature items are actively planned for implementation during development sessions:

### Milestone 1: Distributed Caching Backend
- [ ] Implement `RedisExactCache` adapter using `redis-py` async connection pool.
- [ ] Implement Redis Vector Search (RediSearch) semantic caching for horizontal gateway scaling.

### Milestone 2: Upstream Provider Expansion
- [ ] Add native Anthropic Claude provider (`/v1/messages` schema translation).
- [ ] Add Google Gemini provider adapter (`google-genai` REST integration).
- [ ] Add local Ollama provider for completely offline local model routing.

### Milestone 3: Advanced Guardrails & Canary Tokens
- [ ] Inject hidden canary tokens into system prompts to detect and audit prompt extraction attempts.
- [ ] Add multilingual PII regex models (support European GDPR PII formats).

### Milestone 4: Enterprise Observability
- [ ] Add native Prometheus `/metrics` exporter (counter, histogram for latency quantiles).
- [ ] OpenTelemetry trace propagation (`traceparent` header forwarding).

---

## Pull Request Guidelines

- Branch naming: `feat/<feature-name>`, `fix/<bug-name>`, `perf/<improvement>`.
- Commit conventions: Standard conventional commits (`feat: ...`, `fix: ...`, `test: ...`, `chore: ...`).
- Every new provider or guardrail must include comprehensive unit tests in `tests/`.
