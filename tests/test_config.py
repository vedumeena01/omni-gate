"""Tests for application settings and configuration loading."""

from src.core.config import Settings


def test_default_settings():
    """Verify default settings instantiation."""
    config = Settings()
    assert config.app_name == "OmniGate"
    assert config.port == 8000
    assert config.cache_enabled is True
    assert config.semantic_similarity_threshold == 0.88
    assert config.guardrails_enabled is True
    assert config.failure_threshold == 3


def test_env_override(monkeypatch):
    """Verify environment variable overrides with prefix OMNIGATE_."""
    monkeypatch.setenv("OMNIGATE_APP_NAME", "CustomGate")
    monkeypatch.setenv("OMNIGATE_PORT", "9000")
    monkeypatch.setenv("OMNIGATE_CACHE_ENABLED", "false")
    monkeypatch.setenv("OMNIGATE_SEMANTIC_SIMILARITY_THRESHOLD", "0.95")

    config = Settings()
    assert config.app_name == "CustomGate"
    assert config.port == 9000
    assert config.cache_enabled is False
    assert config.semantic_similarity_threshold == 0.95
