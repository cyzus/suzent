"""Tests for the model capability sync automation wrapper."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _load_script_main():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "sync_model_capabilities.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sync_model_capabilities", script_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def test_main_sets_repo_write_flag_and_prints_json(capsys, monkeypatch):
    monkeypatch.delenv("SUZENT_CAPABILITIES_TO_REPO", raising=False)

    async def fake_sync() -> dict[str, int]:
        return {"openai": 2, "anthropic": 1}

    result = _load_script_main()(["--to-repo", "--json"], sync_func=fake_sync)

    assert result == 0
    assert os.environ["SUZENT_CAPABILITIES_TO_REPO"] == "1"
    assert capsys.readouterr().out == '{"anthropic": 1, "openai": 2}\n'
