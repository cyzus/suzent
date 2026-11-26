"""The OS keyring backend reads each item once per process."""

from __future__ import annotations

import keyring
import pytest
from keyring.backend import KeyringBackend as _Base
from keyring.errors import KeyringError, PasswordDeleteError

from suzent.core.secrets import KeyringBackend


class CountingKeyring(_Base):
    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}
        self.reads: list[str] = []
        self.deny: set[str] = set()

    def get_password(self, service: str, username: str) -> str | None:
        self.reads.append(username)
        if username in self.deny:
            raise KeyringError("User canceled the operation.")
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise PasswordDeleteError(username)
        del self.store[(service, username)]


@pytest.fixture
def fake() -> CountingKeyring:
    previous = keyring.get_keyring()
    backend = CountingKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_reads_each_item_once(fake: CountingKeyring) -> None:
    fake.store[("suzent", "OPENAI_API_KEY")] = "sk-1"
    backend = KeyringBackend()
    assert backend.get("OPENAI_API_KEY") == "sk-1"
    assert backend.get("OPENAI_API_KEY") == "sk-1"
    assert backend.get("MISSING") is None
    assert backend.get("MISSING") is None
    assert fake.reads == ["OPENAI_API_KEY", "MISSING"]


def test_writes_update_the_cache(fake: CountingKeyring) -> None:
    backend = KeyringBackend()
    backend.set("A", "1")
    backend.set("B", "2")
    assert backend.get("A") == "1"
    assert sorted(backend.list_keys()) == ["A", "B"]
    backend.delete("A")
    assert backend.get("A") is None
    assert backend.list_keys() == ["B"]
    assert "A" not in fake.reads


def test_a_refused_read_is_not_asked_again(fake: CountingKeyring) -> None:
    fake.deny.add("ANTHROPIC_API_KEY")
    backend = KeyringBackend()
    assert backend.get("ANTHROPIC_API_KEY") is None
    assert backend.get("ANTHROPIC_API_KEY") is None
    assert fake.reads.count("ANTHROPIC_API_KEY") == 1


def test_vault_copies_per_key_items_once(fake: CountingKeyring) -> None:
    from suzent.core.secrets import KeychainVaultBackend

    fake.store[("suzent", "__suzent_keys__")] = "A\x00B"
    fake.store[("suzent", "A")] = "1"
    fake.store[("suzent", "B")] = "2"
    first = KeychainVaultBackend()
    assert first.get("A") == "1"
    assert first.list_keys() == ["A", "B"]
    assert fake.store[("suzent", "A")] == "1"

    fake.reads.clear()
    second = KeychainVaultBackend()
    assert second.get("B") == "2"
    assert second.get("A") == "1"
    assert fake.reads == ["__suzent_vault__"]


def test_vault_writes_stay_in_one_item(fake: CountingKeyring) -> None:
    from suzent.core.secrets import KeychainVaultBackend

    backend = KeychainVaultBackend()
    backend.set("A", "1")
    backend.set("B", "2")
    backend.delete("A")
    assert set(fake.store) == {("suzent", "__suzent_vault__")}
    fresh = KeychainVaultBackend()
    assert fresh.list_keys() == ["B"]


def test_vault_is_not_written_after_a_refused_read(fake: CountingKeyring) -> None:
    from suzent.core.secrets import KeychainVaultBackend

    fake.store[("suzent", "__suzent_keys__")] = "A\x00B"
    fake.store[("suzent", "A")] = "1"
    fake.store[("suzent", "B")] = "2"
    fake.deny.add("B")
    backend = KeychainVaultBackend()
    assert backend.get("A") == "1"
    assert backend.get("B") is None
    assert ("suzent", "__suzent_vault__") not in fake.store


def test_refused_vault_asks_for_nothing_else(fake: CountingKeyring) -> None:
    from suzent.core.secrets import KeychainVaultBackend

    fake.store[("suzent", "__suzent_keys__")] = "A"
    fake.store[("suzent", "A")] = "1"
    fake.deny.add("__suzent_vault__")
    backend = KeychainVaultBackend()
    assert backend.get("A") is None
    assert backend.list_keys() == []
    assert fake.reads == ["__suzent_vault__"]


def test_vault_write_keeps_another_process_change(fake: CountingKeyring) -> None:
    from suzent.core.secrets import KeychainVaultBackend

    ours = KeychainVaultBackend()
    theirs = KeychainVaultBackend()
    ours.set("A", "1")
    theirs.set("B", "2")
    ours.set("C", "3")
    assert KeychainVaultBackend().list_keys() == ["A", "B", "C"]
