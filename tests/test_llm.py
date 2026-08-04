import pytest
import os
from unittest.mock import patch, MagicMock
from core.llm import (
    _normalize_lm_host,
    _resolve_anthropic_base_url,
    _is_quota_error,
    _is_rate_or_quota_error,
    _env_int
)

def test_normalize_lm_host():
    assert _normalize_lm_host("http://localhost:1234") == "localhost:1234"
    assert _normalize_lm_host("https://127.0.0.1:8080/") == "127.0.0.1:8080"
    assert _normalize_lm_host("ws://test.com") == "test.com"
    assert _normalize_lm_host(None) is None

@patch.dict(os.environ, {}, clear=True)
def test_env_int():
    assert _env_int("NOT_SET", 10, 0, 100) == 10
    
    with patch.dict(os.environ, {"SET_VAL": "50"}):
        assert _env_int("SET_VAL", 10, 0, 100) == 50
        
    with patch.dict(os.environ, {"SET_VAL": "200"}):
        assert _env_int("SET_VAL", 10, 0, 100) == 100 # capped at max
        
    with patch.dict(os.environ, {"SET_VAL": "-10"}):
        assert _env_int("SET_VAL", 10, 0, 100) == 0 # capped at min

@patch.dict(os.environ, {}, clear=True)
def test_resolve_anthropic_base_url_default():
    assert _resolve_anthropic_base_url() == "https://aiprimetech.io"

@patch.dict(os.environ, {"ANTHROPIC_BASE_URL": "official"})
def test_resolve_anthropic_base_url_official():
    assert _resolve_anthropic_base_url() == "https://api.anthropic.com"

@patch.dict(os.environ, {"ANTHROPIC_BASE_URL": "https://my-proxy.com"})
def test_resolve_anthropic_base_url_custom():
    assert _resolve_anthropic_base_url() == "https://my-proxy.com"

def test_is_quota_error():
    # Errors that should be fatal
    assert _is_quota_error("You exceeded your free-models-per-day quota") is True
    assert _is_quota_error("Billing issue detected") is True
    assert _is_quota_error("Insufficient credits") is True
    assert _is_quota_error("Limite quotidienne atteinte") is True
    
    # Errors that are transient
    assert _is_quota_error("You exceeded your PerMinute quota") is False
    assert _is_quota_error("Rate limit exceeded 10 requests per minute") is False
    
    # Not quota errors
    assert _is_quota_error("Internal server error") is False

def test_is_rate_or_quota_error():
    assert _is_rate_or_quota_error("Resource_exhausted: quota") is True
    assert _is_rate_or_quota_error("429 too many requests") is True
    assert _is_rate_or_quota_error("You exceeded your daily limit") is True
    assert _is_rate_or_quota_error("Syntax error") is False
