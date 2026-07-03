from __future__ import annotations

import base64
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

from suzent.core.secrets import SecretManager, get_secret_manager
from suzent.sync.models import (
    DeviceRegistration,
    EncryptedSecretBundle,
    MnemonicKdfParams,
    SecretBundlesFile,
    SyncProfile,
)
from suzent.sync.mnemonic import (
    decrypt as mnemonic_decrypt,
    derive_key,
    encrypt as mnemonic_encrypt,
    mnemonic_fingerprint,
    new_salt,
    validate_mnemonic,
)
from suzent.sync.shibboleth import (
    derive_fernet_key,
    new_kdf_params,
    validate_shibboleth,
    verify_against_ciphertext,
)

SECRET_BUNDLES_PATH = "_sync/secrets/bundles.json"


def _device_name() -> str:
    return platform.node() or "unknown"


class EncryptedSecretSync:
    def __init__(self, *, secret_manager: SecretManager | None = None) -> None:
        self.secret_manager = secret_manager or get_secret_manager()

    # ------------------------------------------------------------------
    # Mnemonic-based (format_version 2) API
    # ------------------------------------------------------------------

    def export_bundles_mnemonic(
        self,
        profile: SyncProfile,
        mnemonic: str,
        *,
        keys: list[str] | None = None,
        existing_file: SecretBundlesFile | None = None,
    ) -> SecretBundlesFile:
        words = validate_mnemonic(mnemonic)
        phrase = " ".join(words)
        fingerprint = mnemonic_fingerprint(phrase)

        # Reuse the existing salt when merging into a same-phrase vault so previously
        # stored ciphertexts (for keys this device isn't re-exporting) stay
        # decryptable. Only mint a fresh salt for a brand-new / re-keyed vault.
        can_merge = (
            existing_file is not None
            and isinstance(existing_file.kdf, MnemonicKdfParams)
            and existing_file.mnemonic_fingerprint == fingerprint
        )
        if can_merge:
            salt_b64 = existing_file.kdf.salt  # type: ignore[union-attr]
        else:
            salt_b64 = new_salt()
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        enc_key = derive_key(phrase, salt)

        kdf = MnemonicKdfParams(salt=salt_b64)
        selected_keys = keys or self.secret_manager.list_keys()
        selected_set = set(selected_keys)

        # Start from existing vault entries for keys NOT in this device's selection
        # (so a per-key opt-in push doesn't wipe other devices' keys), then
        # (re)encrypt the selected keys this device holds.
        bundles: list[EncryptedSecretBundle] = []
        if can_merge and existing_file is not None:
            bundles.extend(
                b for b in existing_file.bundles if b.key_name not in selected_set
            )
        written_meta = {
            "written_by": _device_name(),
            "written_at": datetime.now(timezone.utc).isoformat(),
        }
        for key in selected_keys:
            value = self.secret_manager.get(key)
            if not value:
                continue
            ct, nonce = mnemonic_encrypt(value.encode("utf-8"), enc_key)
            bundles.append(
                EncryptedSecretBundle(
                    provider=_provider_from_key(key),
                    key_name=key,
                    ciphertext=ct,
                    nonce=nonce,
                    metadata=dict(written_meta),
                )
            )

        mnemonic_ver = (
            (existing_file.mnemonic_version if existing_file else 0) + 1
            if (
                existing_file is None
                or existing_file.mnemonic_fingerprint != fingerprint
            )
            else (existing_file.mnemonic_version if existing_file else 1)
        )

        devices = list(existing_file.devices) if existing_file else []
        _upsert_device(devices, profile.device_id, _device_name(), mnemonic_ver)

        rotated_by = profile.device_id
        rotated_at = datetime.now(timezone.utc)

        return SecretBundlesFile(
            format_version=2,
            kdf=kdf,
            bundles=bundles,
            mnemonic_version=mnemonic_ver,
            mnemonic_fingerprint=fingerprint,
            rotated_by=rotated_by,
            rotated_at=rotated_at,
            devices=devices,
        )

    def import_bundles_mnemonic(
        self,
        payload: SecretBundlesFile,
        mnemonic: str,
        *,
        only_keys: list[str] | None = None,
    ) -> list[str]:
        """Decrypt and apply vault keys to the local backend.

        ``only_keys`` restricts which keys are applied — used to honor per-key sync
        opt-in (a profile's ``synced_keys``). ``None`` means apply every key in the
        bundle (legacy / all-keys behavior). Keys in the bundle but not in
        ``only_keys`` are left untouched locally.
        """
        if payload.format_version != 2 or not isinstance(
            payload.kdf, MnemonicKdfParams
        ):
            raise ValueError(
                "Not a mnemonic-encrypted bundle (format_version must be 2)"
            )
        words = validate_mnemonic(mnemonic)
        phrase = " ".join(words)
        salt = base64.urlsafe_b64decode(payload.kdf.salt.encode("ascii"))
        enc_key = derive_key(phrase, salt)
        allow = set(only_keys) if only_keys is not None else None
        imported: list[str] = []
        for bundle in payload.bundles:
            if allow is not None and bundle.key_name not in allow:
                continue
            try:
                value = mnemonic_decrypt(bundle.ciphertext, bundle.nonce, enc_key)
            except ValueError as exc:
                raise ValueError("Incorrect mnemonic phrase") from exc
            self.secret_manager.set(bundle.key_name, value.decode("utf-8"))
            imported.append(bundle.key_name)
        return imported

    def overwrite_diff_mnemonic(
        self,
        payload: SecretBundlesFile,
        mnemonic: str,
        *,
        only_keys: list[str] | None = None,
    ) -> list[str]:
        """Return key names whose local value would CHANGE if the vault were applied.

        Used to surface "N keys will change from vault" before a pull overwrites
        local values (vault-is-authority, but visible not silent). Never returns
        values. Keys absent locally count as changes (they'll be added).
        """
        if payload.format_version != 2 or not isinstance(
            payload.kdf, MnemonicKdfParams
        ):
            return []
        words = validate_mnemonic(mnemonic)
        phrase = " ".join(words)
        salt = base64.urlsafe_b64decode(payload.kdf.salt.encode("ascii"))
        enc_key = derive_key(phrase, salt)
        allow = set(only_keys) if only_keys is not None else None
        changed: list[str] = []
        for bundle in payload.bundles:
            if allow is not None and bundle.key_name not in allow:
                continue
            try:
                new_val = mnemonic_decrypt(
                    bundle.ciphertext, bundle.nonce, enc_key
                ).decode("utf-8")
            except ValueError:
                continue
            if self.secret_manager.get(bundle.key_name) != new_val:
                changed.append(bundle.key_name)
        return changed

    def remove_keys_from_vault(
        self, bundle_path: Path, profile: SyncProfile, keys: list[str]
    ) -> tuple[SecretBundlesFile, list[str]]:
        """Drop the given keys from the vault bundle (no decryption needed).

        Returns the updated bundle and the list of key names actually removed. The
        caller writes it back and pushes; other devices see the removal on pull.
        """
        payload = self.read_bundles_file(bundle_path)
        if payload is None:
            raise ValueError("No secret bundles file found")
        drop = set(keys)
        removed = [b.key_name for b in payload.bundles if b.key_name in drop]
        payload.bundles = [b for b in payload.bundles if b.key_name not in drop]
        payload.rotated_by = profile.device_id
        payload.rotated_at = datetime.now(timezone.utc)
        return payload, removed

    def register_device(
        self,
        bundle_path: Path,
        profile: SyncProfile,
        mnemonic: str,
    ) -> SecretBundlesFile:
        """Verify mnemonic against existing bundles and register this device."""
        payload = self.read_bundles_file(bundle_path)
        if payload is None:
            raise ValueError("No secret bundles file found")
        if not self.verify_mnemonic(payload, mnemonic):
            raise ValueError("Incorrect mnemonic phrase")
        devices = list(payload.devices)
        _upsert_device(
            devices, profile.device_id, _device_name(), payload.mnemonic_version
        )
        payload.devices = devices
        return payload

    def rotation_detected(self, bundle_path: Path, profile: SyncProfile) -> dict | None:
        """Return rotation info if the repo has a newer mnemonic_version than this device knows."""
        payload = self.read_bundles_file(bundle_path)
        if payload is None or payload.format_version != 2:
            return None
        my_version = _device_known_version(payload.devices, profile.device_id)
        if my_version is None or my_version >= payload.mnemonic_version:
            return None
        rotator = _device_name_by_id(payload.devices, payload.rotated_by or "")
        return {
            "rotation_detected": True,
            "mnemonic_version": payload.mnemonic_version,
            "rotated_by_device": rotator,
            "rotated_at": payload.rotated_at.isoformat()
            if payload.rotated_at
            else None,
        }

    def inspect_vault(self, bundle_path: Path, profile: SyncProfile) -> dict:
        """Return non-secret facts about the shared secret vault for the UI.

        Never returns any secret value — only key *names*, device metadata, and a
        per-device diff of which keys live where. This is the data the redesigned
        Sync UI needs so a user can see (e.g.) that GEMINI_API_KEY is missing from
        the vault, instead of cracking bundles.json by hand.
        """
        local_keys = sorted(self.secret_manager.list_keys())
        # None synced_keys == legacy "all keys sync"; surface as the full local set so
        # the UI shows everything opted-in by default.
        synced = (
            sorted(profile.synced_keys)
            if profile.synced_keys is not None
            else local_keys
        )
        payload = self.read_bundles_file(bundle_path)
        if payload is None:
            return {
                "exists": False,
                "vault_keys": [],
                "key_meta": {},
                "local_keys": local_keys,
                "local_only_keys": local_keys,
                "vault_only_keys": [],
                "synced_keys": synced,
                "devices": [],
                "this_device_enrolled": False,
                "rotated_by_device": None,
                "rotated_at": None,
                "mnemonic_version": None,
                "mnemonic_fingerprint": None,
            }

        vault_keys = sorted(b.key_name for b in payload.bundles)
        vault_set, local_set = set(vault_keys), set(local_keys)
        enrolled = any(d.device_id == profile.device_id for d in payload.devices)
        # Per-key provenance (who last wrote each key), from bundle metadata.
        key_meta = {
            b.key_name: {
                "written_by": b.metadata.get("written_by"),
                "written_at": b.metadata.get("written_at"),
            }
            for b in payload.bundles
        }
        return {
            "exists": True,
            "vault_keys": vault_keys,
            "key_meta": key_meta,
            "local_keys": local_keys,
            "local_only_keys": sorted(local_set - vault_set),
            "vault_only_keys": sorted(vault_set - local_set),
            "synced_keys": synced,
            "devices": [
                {
                    "device_id": d.device_id,
                    "device_name": d.device_name,
                    "mnemonic_version": d.mnemonic_version,
                }
                for d in payload.devices
            ],
            "this_device_enrolled": enrolled,
            "rotated_by_device": _device_name_by_id(
                payload.devices, payload.rotated_by or ""
            ),
            "rotated_at": payload.rotated_at.isoformat()
            if payload.rotated_at
            else None,
            "mnemonic_version": payload.mnemonic_version,
            "mnemonic_fingerprint": payload.mnemonic_fingerprint,
        }

    # ------------------------------------------------------------------
    # Legacy shibboleth (format_version 1) API — kept for migration
    # ------------------------------------------------------------------

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
        fernet = Fernet(derive_fernet_key(shibboleth, kdf))  # type: ignore[arg-type]
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
        fernet = Fernet(derive_fernet_key(shibboleth, payload.kdf))  # type: ignore[arg-type]
        imported: list[str] = []
        for bundle in payload.bundles:
            value = fernet.decrypt(bundle.ciphertext.encode("utf-8")).decode("utf-8")
            self.secret_manager.set(bundle.key_name, value)
            imported.append(bundle.key_name)
        return imported

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def read_bundles_file(self, bundle_path: Path) -> SecretBundlesFile | None:
        if not bundle_path.is_file():
            return None
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
        if "kdf" not in data:
            raise ValueError(
                "Secret bundles file is missing KDF metadata; "
                "re-push with encrypted API key sync enabled"
            )
        return SecretBundlesFile.model_validate(data)

    def write_bundles_file(self, bundle_path: Path, payload: SecretBundlesFile) -> None:
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def verify_mnemonic(self, payload: SecretBundlesFile, mnemonic: str) -> bool:
        if payload.format_version != 2 or not isinstance(
            payload.kdf, MnemonicKdfParams
        ):
            return False
        if not payload.bundles:
            return True
        words = validate_mnemonic(mnemonic)
        phrase = " ".join(words)
        if (
            payload.mnemonic_fingerprint
            and mnemonic_fingerprint(phrase) != payload.mnemonic_fingerprint
        ):
            return False
        salt = base64.urlsafe_b64decode(payload.kdf.salt.encode("ascii"))
        enc_key = derive_key(phrase, salt)
        sample = payload.bundles[0]
        try:
            mnemonic_decrypt(sample.ciphertext, sample.nonce, enc_key)
            return True
        except ValueError:
            return False

    def verify_shibboleth(self, bundle_path: Path, shibboleth: str) -> bool:
        validate_shibboleth(shibboleth)
        payload = self.read_bundles_file(bundle_path)
        if payload is None or not payload.bundles:
            return True
        if payload.format_version == 2:
            return False
        sample = payload.bundles[0]
        return verify_against_ciphertext(shibboleth, payload.kdf, sample.ciphertext)  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _provider_from_key(key: str) -> str:
    upper = key.upper()
    if upper.endswith("_API_KEY"):
        return upper.removesuffix("_API_KEY").lower()
    return "custom"


def _upsert_device(
    devices: list[DeviceRegistration],
    device_id: str,
    device_name: str,
    mnemonic_version: int,
) -> None:
    for d in devices:
        if d.device_id == device_id:
            d.device_name = device_name
            d.mnemonic_version = mnemonic_version
            return
    devices.append(
        DeviceRegistration(
            device_id=device_id,
            device_name=device_name,
            mnemonic_version=mnemonic_version,
        )
    )


def _device_known_version(
    devices: list[DeviceRegistration], device_id: str
) -> int | None:
    for d in devices:
        if d.device_id == device_id:
            return d.mnemonic_version
    return None


def _device_name_by_id(devices: list[DeviceRegistration], device_id: str) -> str:
    for d in devices:
        if d.device_id == device_id:
            return d.device_name
    return device_id
