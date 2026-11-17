"""Core configuration and settings for OmniGate using Pydantic Settings."""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """OmniGate Application Settings."""

    model_config = SettingsConfigDict(
        env_prefix="OMNIGATE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General App Settings
    app_name: str = "OmniGate"
    app_env: str = Field(default="development", description="development | production | testing")
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    master_api_key: Optional[str] = Field(
        default=None, description="Master API Key required if non-empty"
    )

    # Cache Settings
    cache_enabled: bool = True
    exact_cache_ttl_seconds: int = 3600
    exact_cache_max_size: int = 10000
    semantic_cache_enabled: bool = True
    semantic_similarity_threshold: float = 0.88

    # Guardrails Settings
    guardrails_enabled: bool = True
    pii_masking_enabled: bool = True
    injection_detection_enabled: bool = True
    block_on_injection: bool = True

    # Resiliency: Circuit Breaker & Rate Limiter
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    half_open_success_threshold: int = 2
    rate_limit_enabled: bool = True
    default_requests_per_minute: int = 60
    default_burst_capacity: int = 10

    # Provider & Routing
    default_model: str = "mock-gpt-4o"
    fallback_model: str = "mock-gpt-3.5-turbo"
    upstream_openai_base_url: str = "https://api.openai.com/v1"
    upstream_openai_api_key: Optional[str] = None
    timeout_seconds: float = 30.0
    max_retries: int = 2


settings = Settings()
