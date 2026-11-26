import base64
import json
import sys
import time

from suzent.core.providers import chatgpt_auth


def _jwt(exp: float) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode()
    return f"h.{body.rstrip('=')}.s"


def _write(tmp_path, monkeypatch, data) -> None:
    monkeypatch.setenv("CHATGPT_TOKEN_DIR", str(tmp_path))
    monkeypatch.delitem(
        sys.modules, "litellm.llms.chatgpt.authenticator", raising=False
    )
    if data is not None:
        (tmp_path / "auth.json").write_text(json.dumps(data), encoding="utf-8")


def test_unexpired_token_counts_without_importing_litellm(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {"access_token": _jwt(time.time() + 3600)})
    assert chatgpt_auth.has_unexpired_token_without_litellm() is True
    assert "litellm.llms.chatgpt.authenticator" not in sys.modules


def test_expired_missing_or_unreadable_token_does_not_count(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, {"access_token": "x", "expires_at": time.time() - 5})
    assert chatgpt_auth.has_unexpired_token_without_litellm() is False
    (tmp_path / "auth.json").write_text("{not json", encoding="utf-8")
    assert chatgpt_auth.has_unexpired_token_without_litellm() is False
    (tmp_path / "auth.json").unlink()
    assert chatgpt_auth.has_unexpired_token_without_litellm() is False


def test_defers_to_litellm_once_it_is_loaded(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, None)
    monkeypatch.setitem(sys.modules, "litellm.llms.chatgpt.authenticator", object())
    assert chatgpt_auth.has_unexpired_token_without_litellm() is None
