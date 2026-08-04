import pytest
import os
import json
from unittest.mock import patch, mock_open
from core.utils import (
    load_agents_config, 
    AGENTS_CONFIG, 
    AVAILABLE_MODELS, 
    MODEL_PROVIDERS, 
    get_model_provider,
    get_key_slot,
    get_context_limit,
    get_filtered_models,
    get_default_model
)

@pytest.fixture(autouse=True)
def reset_agents_config():
    """Vider AGENTS_CONFIG avant et après chaque test."""
    AGENTS_CONFIG.clear()
    yield
    AGENTS_CONFIG.clear()

def test_get_model_provider():
    assert get_model_provider("Gemini 3.1 Pro Preview (Standard)") == "gemini"
    assert get_model_provider("Claude Opus 4.8") == "anthropic"
    assert get_model_provider("Gemma 4 (LM Studio Local)") == "lm_studio"
    assert get_model_provider("Unknown Model") == ""

def test_get_key_slot():
    assert get_key_slot("gemini-3.1-pro-preview") == 2
    assert get_key_slot("gemma-4-31b-it") == 1
    assert get_key_slot("") == 1

def test_get_context_limit():
    assert get_context_limit("gemma-4-31b-it") == 256_000
    assert get_context_limit("claude-opus-4-8[1m]") == 1_000_000
    assert get_context_limit("gemini-3.1-pro-preview") == 1_000_000

def test_get_filtered_models():
    # Tester les différents modes d'authentification
    models_api_key = get_filtered_models("api_key")
    assert "Gemini 3.1 Pro Preview (Standard)" in models_api_key
    assert "Claude Opus 4.8" not in models_api_key
    assert "Gemma 4 (LM Studio Local)" not in models_api_key

    models_google_claude = get_filtered_models("google_claude")
    assert "Gemini 3.1 Pro Preview (Standard)" in models_google_claude
    assert "Claude Opus 4.8" in models_google_claude
    assert "Gemma 4 (LM Studio Local)" not in models_google_claude

    models_lm_studio = get_filtered_models("lm_studio")
    assert "Gemma 4 (LM Studio Local)" in models_lm_studio
    assert "Gemini 3.1 Pro Preview (Standard)" not in models_lm_studio

def test_get_default_model():
    assert get_default_model(["Model A", "Model B"]) == "Model A"
    assert get_default_model([]) == ""

@patch("builtins.open", new_callable=mock_open, read_data='{"agent1": {"name": "Test Agent"}}')
@patch("os.path.exists", return_value=False)
def test_load_agents_config_basic(mock_exists, mock_file):
    load_agents_config("coder")
    assert "agent1" in AGENTS_CONFIG
    assert AGENTS_CONFIG["agent1"]["name"] == "Test Agent"
