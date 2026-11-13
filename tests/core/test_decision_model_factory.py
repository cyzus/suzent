import pytest
from pydantic_ai.models.google_decisions import GoogleDecisionsModel
from pydantic_ai.models.openai_decisions import OpenAIDecisionsModel
from pydantic_ai.models.system_one import SystemOneModel

from suzent.core import model_factory
from suzent.core.providers.catalog import ProviderSpec


def _provider(monkeypatch, spec: ProviderSpec, key: str | None = "test-key") -> None:
    monkeypatch.setitem(model_factory.PROVIDER_REGISTRY_BY_ID, spec.id, spec)
    monkeypatch.setattr(model_factory, "resolve_api_key", lambda _provider: key)


@pytest.mark.parametrize(
    ("protocol", "base_url", "model_class"),
    [
        ("gemini", None, GoogleDecisionsModel),
        ("openai", "https://proxy.example/v1", OpenAIDecisionsModel),
        ("system_one", "https://api.typesafe.example", SystemOneModel),
    ],
)
def test_decision_models_follow_the_providers_protocol(
    monkeypatch, protocol, base_url, model_class
):
    spec = ProviderSpec(
        id="acme",
        label="Acme",
        api_type="openai",
        base_url=base_url,
        decisions_protocol=protocol,
    )
    _provider(monkeypatch, spec)

    model = model_factory.create_decision_model("acme/decider-1")

    assert isinstance(model, model_class)
    assert model.model_name == "decider-1"


def test_system_one_needs_a_base_url(monkeypatch):
    spec = ProviderSpec(
        id="acme", label="Acme", api_type="openai", decisions_protocol="system_one"
    )
    _provider(monkeypatch, spec)

    with pytest.raises(RuntimeError, match="no base URL"):
        model_factory.create_decision_model("acme/decider-1")


def test_providers_without_a_protocol_have_no_decision_models(monkeypatch):
    _provider(monkeypatch, ProviderSpec(id="acme", label="Acme", api_type="openai"))

    with pytest.raises(RuntimeError, match="doesn't serve decision models"):
        model_factory.create_decision_model("acme/chat-1")


def test_shipped_providers_declare_their_protocols():
    from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID

    assert PROVIDER_REGISTRY_BY_ID["openai"].decisions_protocol == "openai"
    assert PROVIDER_REGISTRY_BY_ID["gemini"].decisions_protocol == "gemini"
    assert PROVIDER_REGISTRY_BY_ID["litellm_proxy"].decisions_protocol == "openai"
