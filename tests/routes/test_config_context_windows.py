"""The config listing carries a context budget per model.

The panel has to show the maximum for the model in the selector the moment it
changes. One global number could not do that: it described whichever model
happened to be the default, so a chat on a 1M-token model was drawn against the
128k default's budget — or against the unknown-model fallback.
"""

from starlette.testclient import TestClient

from suzent.core.model_registry import ModelCapabilities
from suzent.routes import config_routes
from suzent.server import app

client = TestClient(app)

CAPS = {
    "gemini/big": ModelCapabilities(
        max_input_tokens=1_048_576, max_output_tokens=65_536
    ),
    "openai/small": ModelCapabilities(max_input_tokens=128_000),
}


def _fake_registry(monkeypatch, default_model="gemini/big"):
    monkeypatch.setattr(
        config_routes, "get_enabled_models_from_db", lambda: list(CAPS) + ["who/knows"]
    )
    monkeypatch.setattr(config_routes, "get_default_chat_model", lambda: default_model)
    monkeypatch.setattr(
        "suzent.core.model_registry.get_model_registry",
        lambda: type("R", (), {"get_capabilities": staticmethod(CAPS.get)})(),
    )


def test_every_enabled_model_reports_its_own_window(monkeypatch):
    _fake_registry(monkeypatch)

    windows = client.get("/config").json()["contextWindows"]

    assert windows["gemini/big"] == 1_048_576
    assert windows["openai/small"] == 128_000


def test_unknown_model_gets_the_conservative_fallback(monkeypatch):
    _fake_registry(monkeypatch)

    windows = client.get("/config").json()["contextWindows"]

    # Overshooting a real window is a hard provider error; undershooting only
    # compacts early, so an unregistered model is budgeted low.
    assert windows["who/knows"] == 200_000


def test_global_default_is_not_the_selected_model(monkeypatch):
    # The bug this replaced: an unregistered default model dragged every chat's
    # displayed maximum down to the fallback, whatever model the chat was on.
    _fake_registry(monkeypatch, default_model="who/knows")

    payload = client.get("/config").json()

    assert payload["maxContextTokens"] == 200_000
    assert payload["contextWindows"]["gemini/big"] == 1_048_576


def test_chat_load_reports_the_budget_of_that_chat_s_model(monkeypatch, tmp_path):
    """Opening a chat carries a limit for the model that chat runs on.

    The panel has to be right the moment a chat opens, without waiting for a turn,
    and a limit stored while another model was selected must not outlive the
    switch — that stale value is what kept the old maximum on screen.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route

    from suzent.database.models import ChatModel
    from suzent.routes.chat_routes import get_chat

    _fake_registry(monkeypatch)
    tmp_project = tmp_path

    chat = ChatModel(
        id="c1",
        title="a chat",
        config={"model": "openai/small"},
        messages=[],
        context_usage={"context_tokens": 50_000, "context_limit": 1_048_576},
    )

    class _Db:
        @staticmethod
        def get_chat(_id):
            return chat

        @staticmethod
        def get_project_dir(_id):
            return tmp_project

    monkeypatch.setattr("suzent.routes.chat_routes.get_database", lambda: _Db())

    app = Starlette(routes=[Route("/chats/{chat_id}", get_chat)])
    usage = TestClient(app).get("/chats/c1").json()["contextUsage"]

    assert usage["context_limit"] == 128_000
    assert usage["context_tokens"] == 50_000
