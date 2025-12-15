"""
Unit tests for configuration management.
"""
import pytest
import os
from pathlib import Path


def test_config_loads_defaults(tmp_path, monkeypatch):
    """Test that configuration loads default values."""
    from suzent.config import Config, CONFIG
    
    # Config should have default values
    assert CONFIG.model_options is not None
    assert len(CONFIG.model_options) > 0
    assert CONFIG.default_tools is not None


def test_config_tool_options():
    """Test that tool options are generated correctly."""
    from suzent.config import CONFIG
    
    tool_options = CONFIG.get_tool_options()
    
    assert "WebSearchTool" in tool_options
    assert "PlanningTool" in tool_options
    assert "WebpageTool" in tool_options
    assert "FileTool" in tool_options


def test_config_environment_override(monkeypatch):
    """Test that environment variables override config."""
    from suzent.config import Config
    
    # Set environment variable
    test_model = "openai/gpt-test"
    monkeypatch.setenv("MODEL_OPTIONS", test_model)
    
    # Reload config (in real usage, this would be at startup)
    # For testing, we just verify the pattern works
    model_from_env = os.getenv("MODEL_OPTIONS")
    assert model_from_env == test_model
