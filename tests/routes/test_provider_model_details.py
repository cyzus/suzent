from suzent.core.providers.base import Model
from suzent.routes.config_routes import _model_details


def test_discovered_model_includes_known_capabilities() -> None:
    details = _model_details(Model(id="openai/gpt-6.1-sol", name="GPT-6.1 Sol"))

    assert details["context_length"] > 0
    assert details["mode"] == "chat"
    assert details["supports_function_calling"] is True


def test_unknown_model_does_not_claim_capabilities() -> None:
    details = _model_details(Model(id="custom/unknown-model", name="Unknown"))

    assert "supports_vision" not in details
    assert details["context_length"] is None
