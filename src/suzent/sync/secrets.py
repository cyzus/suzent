from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

from suzent.core.secrets import SecretManager, get_secret_manager
from suzent.sync.models import EncryptedSecretBundle, SecretBundlesFile, SyncProfile
from suzent.sync.shibboleth import (
    derive_fernet_key,
    new_kdf_params,
    validate_shibboleth,
    verify_against_ciphertext,
)

SECRET_BUNDLES_PATH = "_sync/secrets/bundles.json"


class EncryptedSecretSync:
    def __init__(self, *, secret_manager: SecretManager | None = None) -> None:
        self.secret_manager = secret_manager or get_secret_manager()

    def export_bundles(
        self,
        profile: SyncProfile,
        shibboleth: str,
        *,
        keys: list[str] | None = None,
        existing_file: SecretBundlesFile | None = None,
    ) -> SecretBundlesFile:
        if not profile.encrypted_secret_sync_enabled:
            return SecretBundlesFile(kdf=new_kdf_params(), bundles=[])
        validate_shibboleth(shibboleth)
        kdf = existing_file.kdf if existing_file else new_kdf_params()
        fernet = Fernet(derive_fernet_key(shibboleth, kdf))
        selected_keys = keys or self.secret_manager.list_keys()
        bundles: list[EncryptedSecretBundle] = []
        for key in selected_keys:
            value = self.secret_manager.get(key)
            if not value:
                continue
            token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
            bundles.append(
                EncryptedSecretBundle(
                    provider=_provider_from_key(key),
                    key_name=key,
                    ciphertext=token,
                    nonce=base64.urlsafe_b64encode(os.urandom(12)).decode("ascii"),
                )
            )
        return SecretBundlesFile(kdf=kdf, bundles=bundles)

    def import_bundles(self, payload: SecretBundlesFile, shibboleth: str) -> list[str]:
        validate_shibboleth(shibboleth)
        fernet = Fernet(derive_fernet_key(shibboleth, payload.kdf))
        imported: list[str] = []
        for bundle in payload.bundles:
            value = fernet.decrypt(bundle.ciphertext.encode("utf-8")).decode("utf-8")
            self.secret_manager.set(bundle.key_name, value)
            imported.append(bundle.key_name)
        return imported

    def read_bundles_file(self, bundle_path: Path) -> SecretBundlesFile | None:
        if not bundle_path.is_file():
            return None
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
        if "kdf" not in data:
            raise ValueError(
                "Secret bundles file is missing Shibboleth KDF metadata; "
                "re-push with Shibboleth (passphrase) enabled"
            )
        return SecretBundlesFile.model_validate(data)

    def write_bundles_file(self, bundle_path: Path, payload: SecretBundlesFile) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def verify_shibboleth(self, bundle_path: Path, shibboleth: str) -> bool:
        validate_shibboleth(shibboleth)
        payload = self.read_bundles_file(bundle_path)
        if payload is None or not payload.bundles:
            return True
        sample = payload.bundles[0]
        return verify_against_ciphertext(shibboleth, payload.kdf, sample.ciphertext)


def _provider_from_key(key: str) -> str:
    upper = key.upper()
    if upper.endswith("_API_KEY"):
        return upper.removesuffix("_API_KEY").lower()
    return "custom"
