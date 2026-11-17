"""OmniGate: Production AI Gateway FastAPI application."""

from contextlib import asynccontextmanager
import json
import time
from typing import AsyncIterator, Optional
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from src.cache.exact import ExactMatchCache
from src.cache.semantic import SemanticCache
from src.core.config import Settings, settings
from src.guardrails.base import (
    GuardrailPipeline,
    GuardrailViolationException,
)
from src.guardrails.injection import PromptInjectionDetector
from src.guardrails.pii import PIISanitizer
from src.models.chat import (
    ChatCompletionRequest,
)
from src.providers.http_provider import HttpProvider
from src.providers.mock import MockProvider
from src.resiliency.rate_limiter import RateLimiter
from src.resiliency.router import (
    AllProvidersFailedException,
    ResilientRouter,
)
from src.telemetry.metrics import MetricsTracker


class GatewayContext:
    """Dependency container holding singleton instances of gateway subsystems."""

    def __init__(self, cfg: Settings):
        self.config = cfg
        self.start_time = time.time()
        self.metrics = MetricsTracker()
        self.exact_cache = ExactMatchCache(
            max_size=cfg.exact_cache_max_size,
            default_ttl_seconds=cfg.exact_cache_ttl_seconds,
        )
        self.semantic_cache = SemanticCache(
            similarity_threshold=cfg.semantic_similarity_threshold
        )
        self.rate_limiter = RateLimiter(
            requests_per_minute=cfg.default_requests_per_minute,
            burst_capacity=cfg.default_burst_capacity,
        )
        self.guardrails = GuardrailPipeline(
            guardrails=[
                PIISanitizer(),
                PromptInjectionDetector(),
            ],
            block_on_violation=cfg.block_on_injection,
        )

        # Initialize upstream providers
        primary = (
            HttpProvider(
                provider_name="upstream-primary",
                base_url=cfg.upstream_openai_base_url,
                api_key=cfg.upstream_openai_api_key,
                timeout=cfg.timeout_seconds,
            )
            if cfg.upstream_openai_api_key
            else MockProvider(
                provider_name="mock-primary",
                default_reply="OmniGate Primary Mock Response.",
            )
        )
        fallback = MockProvider(
            provider_name="mock-fallback",
            default_reply="OmniGate Fallback Resilient Response.",
        )

        self.router = ResilientRouter(
            providers=[primary, fallback],
            failure_threshold=cfg.failure_threshold,
            recovery_timeout=cfg.recovery_timeout_seconds,
        )


def create_app(cfg: Optional[Settings] = None) -> FastAPI:
    """Application factory for OmniGate."""
    active_config = cfg or settings
    ctx = GatewayContext(active_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = ctx
        yield

    app = FastAPI(
        title="OmniGate",
        description="Production AI Gateway, Guardrails & Evaluation Harness",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.ctx = ctx

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", status_code=status.HTTP_200_OK)
    async def health():
        """Health check and uptime status."""
        uptime = round(time.time() - ctx.start_time, 2)
        return {
            "status": "healthy",
            "uptime_seconds": uptime,
            "version": "0.1.0",
            "environment": active_config.app_env,
        }

    @app.get("/metrics", status_code=status.HTTP_200_OK)
    async def get_metrics():
        """Return runtime telemetry, cache hit ratios, and latency distribution."""
        return await ctx.metrics.get_summary()

    @app.get("/v1/models", status_code=status.HTTP_200_OK)
    async def list_models():
        """List available models."""
        return {
            "object": "list",
            "data": [
                {"id": active_config.default_model, "object": "model", "owned_by": "omni-gate"},
                {"id": active_config.fallback_model, "object": "model", "owned_by": "omni-gate"},
            ],
        }

    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(
        payload: ChatCompletionRequest,
        req: Request,
        authorization: Optional[str] = Header(None),
    ):
        """OpenAI-compatible Chat Completion proxy endpoint with caching and guardrails."""
        start_time = time.perf_counter()

        # 1. Master API key check (if enabled)
        if active_config.master_api_key:
            expected = f"Bearer {active_config.master_api_key}"
            if not authorization or authorization != expected:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or missing Authorization header.",
                )

        # 2. Rate Limiting Check
        client_key = authorization or (req.client.host if req.client else "anonymous")
        if active_config.rate_limit_enabled:
            allowed, retry_after = await ctx.rate_limiter.check_rate_limit(client_key)
            if not allowed:
                await ctx.metrics.record_request(rate_limited=True)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "message": "Rate limit exceeded. Please throttle requests.",
                            "type": "rate_limit_error",
                            "retry_after": retry_after,
                        }
                    },
                    headers={"Retry-After": str(int(retry_after or 1))},
                )

        # 3. Guardrails Inspection
        if active_config.guardrails_enabled:
            for message in payload.messages:
                if message.role in ("user", "system"):
                    try:
                        message.content = await ctx.guardrails.execute(message.content)
                    except GuardrailViolationException as gve:
                        await ctx.metrics.record_request(guardrail_blocked=True)
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content={
                                "error": {
                                    "message": f"Prompt rejected: {gve.violation_type}",
                                    "type": "guardrail_violation",
                                    "details": gve.details,
                                }
                            },
                        )

        # 4. Two-Tier Caching (Non-streaming only)
        if not payload.stream and active_config.cache_enabled:
            # Tier 1: Exact Match
            exact_hit = await ctx.exact_cache.get(payload)
            if exact_hit:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                exact_hit.latency_ms = round(elapsed_ms, 2)
                await ctx.metrics.record_request(
                    success=True,
                    latency_ms=elapsed_ms,
                    cache_type="exact",
                    prompt_tokens=exact_hit.usage.prompt_tokens,
                    completion_tokens=exact_hit.usage.completion_tokens,
                )
                headers = {"X-Cache": "HIT-EXACT", "X-Latency-Ms": str(round(elapsed_ms, 2))}
                return JSONResponse(content=exact_hit.model_dump(), headers=headers)

            # Tier 2: Semantic Match
            if active_config.semantic_cache_enabled:
                semantic_res = await ctx.semantic_cache.get(payload)
                if semantic_res:
                    semantic_hit, score = semantic_res
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    semantic_hit.latency_ms = round(elapsed_ms, 2)
                    await ctx.metrics.record_request(
                        success=True,
                        latency_ms=elapsed_ms,
                        cache_type="semantic",
                        prompt_tokens=semantic_hit.usage.prompt_tokens,
                        completion_tokens=semantic_hit.usage.completion_tokens,
                    )
                    headers = {
                        "X-Cache": "HIT-SEMANTIC",
                        "X-Similarity-Score": str(score),
                        "X-Latency-Ms": str(round(elapsed_ms, 2)),
                    }
                    return JSONResponse(content=semantic_hit.model_dump(), headers=headers)

        # 5. Upstream Model Execution via Resilient Router
        try:
            if payload.stream:
                # Streaming SSE flow
                async def sse_event_stream() -> AsyncIterator[str]:
                    stream_tokens = 0
                    try:
                        async for chunk in ctx.router.execute_stream(payload):
                            for choice in chunk.choices:
                                if choice.delta.content:
                                    stream_tokens += len(choice.delta.content.split())
                            yield f"data: {json.dumps(chunk.model_dump(exclude_none=True))}\n\n"
                        yield "data: [DONE]\n\n"
                        elapsed_ms = (time.perf_counter() - start_time) * 1000
                        await ctx.metrics.record_request(
                            success=True,
                            latency_ms=elapsed_ms,
                            cache_type="none",
                            prompt_tokens=max(1, len(payload.get_last_user_prompt().split())),
                            completion_tokens=max(1, stream_tokens),
                        )
                    except Exception as err:
                        await ctx.metrics.record_request(success=False)
                        yield f"data: {json.dumps({'error': str(err)})}\n\n"

                return StreamingResponse(
                    sse_event_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )

            # Non-streaming execution
            response = await ctx.router.execute(payload)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            response.latency_ms = round(elapsed_ms, 2)

            # Populate caches on successful generation
            if active_config.cache_enabled:
                await ctx.exact_cache.set(payload, response)
                if active_config.semantic_cache_enabled:
                    await ctx.semantic_cache.set(payload, response)

            await ctx.metrics.record_request(
                success=True,
                latency_ms=elapsed_ms,
                cache_type="none",
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

            headers = {"X-Cache": "MISS", "X-Latency-Ms": str(round(elapsed_ms, 2))}
            return JSONResponse(content=response.model_dump(), headers=headers)

        except AllProvidersFailedException as apfe:
            await ctx.metrics.record_request(success=False)
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={
                    "error": {
                        "message": "All upstream LLM providers failed.",
                        "type": "upstream_gateway_error",
                        "provider_errors": apfe.errors,
                    }
                },
            )

    return app


app = create_app()


def run_server() -> None:
    """CLI Entrypoint to run OmniGate using Uvicorn."""
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
