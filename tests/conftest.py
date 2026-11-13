"""Shared pytest fixtures and configuration."""

import os
import shutil
import tempfile
import uuid
from collections.abc import Callable

import pytest
from cryptography.fernet import Fernet
from pydantic_ai.models.decision import (
    ChoiceAnswer,
    DecisionModel,
    DecisionRequest,
    DecisionResponse,
    NoulAnswer,
)

# suzent.config resolves DATA_DIR once at import, and test modules import the app
# during collection, before any fixture runs. Without this, get_database() and
# config writes land in the real ~/.suzent (e.g. test volumes like C:/data showing
# up in the desktop app). The marker keeps the dir non-empty so the legacy
# repo-local .suzent migration does not copy into it.
_session_data_dir: str | None = None
if "SUZENT_DATA_DIR" not in os.environ:
    _session_data_dir = tempfile.mkdtemp(prefix="suzent_test_data_")
    open(os.path.join(_session_data_dir, ".pytest"), "w").close()
    os.environ["SUZENT_DATA_DIR"] = _session_data_dir

from suzent.database import ChatDatabase  # noqa: E402


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _session_data_dir is None:
        return
    import suzent.database as database

    if database._db_instance is not None:
        database._db_instance.engine.dispose()
    shutil.rmtree(_session_data_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path_factory, monkeypatch):
    """Default every test's SUZENT_DATA_DIR to a temp dir so nothing can write
    into the real ~/.suzent (sync profiles, secrets, config). Tests that need a
    specific data dir still set SUZENT_DATA_DIR themselves, overriding this.

    Only applies when the test hasn't already set it (some fixtures set it in
    their own body, which runs after autouse — so we skip if already present).
    """
    if "SUZENT_DATA_DIR" not in os.environ:
        monkeypatch.setenv(
            "SUZENT_DATA_DIR", str(tmp_path_factory.mktemp("suzent_data"))
        )

    # Force a keyring-free secret backend for the whole suite. Otherwise tests
    # that touch secrets or sync profiles depend on an OS
    # keyring being installed, which fails on headless CI/Linux with
    # NoKeyringError. Reset the cached singleton so the choice takes effect.
    if "SUZENT_SECRET_BACKEND" not in os.environ:
        monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")
    from suzent.core import secrets

    secrets._instance = None
    yield
    secrets._instance = None


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    monkeypatch.setenv("SUZENT_USER_CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("SUZENT_SECRET_DB_PATH", str(tmp_path / "secrets.db"))
    monkeypatch.setenv("SUZENT_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SUZENT_SECRET_BACKEND", "encrypted_sqlite")

    from suzent.core import secrets

    secrets._instance = None

    # Inside tmp_path so the chat logs next to the database are cleaned up too.
    database = ChatDatabase(str(tmp_path / "chats.db"))
    yield database

    # Dispose engine to release file locks (Windows)
    database.engine.dispose()


@pytest.fixture
def unique_id():
    """Generate a unique test ID."""
    return f"test-{uuid.uuid4().hex[:12]}"


class FakeDecisionModel(DecisionModel):
    """Picks ``choose(question_key, options)`` for each pick-one, "yes" for each yes/no.

    ``requests`` keeps every request it was sent; ``fail`` makes every call raise.
    """

    def __init__(
        self,
        choose: Callable[[str, list[str]], str] | None = None,
        *,
        confidence: float = 0.9,
        fail: bool = False,
    ) -> None:
        super().__init__()
        self._choose = choose or (lambda _key, options: options[0])
        self._confidence = confidence
        self._fail = fail
        self.requests: list[DecisionRequest] = []

    @property
    def model_name(self) -> str:
        return "fake-decider"

    @property
    def system(self) -> str:
        return "fake"

    @property
    def base_url(self) -> None:
        return None

    async def decide(
        self, request: DecisionRequest, model_settings
    ) -> DecisionResponse:
        self.requests.append(request)
        if self._fail:
            raise RuntimeError("decision backend down")
        answers = {}
        for key, question in request.questions.items():
            if question.type == "choice":
                options = list(question.criteria)
                pick = self._choose(key, options)
                rest = (1 - self._confidence) / max(len(options) - 1, 1)
                answers[key] = ChoiceAnswer(
                    choice=pick,
                    confidence=self._confidence,
                    probabilities={
                        o: self._confidence if o == pick else rest for o in options
                    },
                )
            else:
                answers[key] = NoulAnswer(noul=0.95)
        return DecisionResponse(answers=answers, model_name=self.model_name)


@pytest.fixture
def fake_decision_model() -> type:
    """A decision model that picks options a test chooses; see ``FakeDecisionModel``."""
    return FakeDecisionModel
