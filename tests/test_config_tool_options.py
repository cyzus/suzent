"""Unit tests for lazy tool-catalog discovery on ConfigModel."""

import importlib

import pytest

config = importlib.import_module("suzent.config")


@pytest.fixture
def counting_discovery(monkeypatch):
    calls = []

    def _discover():
        calls.append(1)
        return ["GrepTool", "WebSearchTool"]

    monkeypatch.setattr(config, "get_tool_options", _discover)
    return calls


def test_load_from_files_leaves_discovery_for_first_use(
    monkeypatch, counting_discovery
):
    cfg = config.ConfigModel(default_tools=["GrepTool"])

    assert not cfg.tool_options
    assert counting_discovery == []


def test_ensure_tool_options_merges_discovery_with_defaults(counting_discovery):
    cfg = config.ConfigModel(default_tools=["GrepTool", "ReadFileTool"])

    assert cfg.ensure_tool_options() == ["GrepTool", "WebSearchTool", "ReadFileTool"]
    assert counting_discovery == [1]


def test_ensure_tool_options_discovers_only_once(counting_discovery):
    cfg = config.ConfigModel(default_tools=["GrepTool"])

    cfg.ensure_tool_options()
    cfg.ensure_tool_options()

    assert counting_discovery == [1]


def test_ensure_tool_options_respects_a_configured_catalog(counting_discovery):
    cfg = config.ConfigModel(tool_options=["GrepTool"], default_tools=["ReadFileTool"])

    assert cfg.ensure_tool_options() == ["GrepTool"]
    assert counting_discovery == []


def test_ensure_tool_options_falls_back_to_defaults_when_discovery_fails(monkeypatch):
    def _boom():
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(config, "get_tool_options", _boom)
    cfg = config.ConfigModel(default_tools=["GrepTool"])

    assert cfg.ensure_tool_options() == ["GrepTool"]
