from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from suzent.sync.models import ShibbolethKdfParams

MIN_SHIBBOLETH_LENGTH = 12
DEFAULT_KDF_ITERATIONS = 600_000
KDF_ALGORITHM = "pbkdf2-sha256"


def validate_shibboleth(passphrase: str) -> None:
    if len(passphrase) < MIN_SHIBBOLETH_LENGTH:
        raise ValueError(
            f"Shibboleth (passphrase) must be at least {MIN_SHIBBOLETH_LENGTH} characters"
        )


def new_kdf_params(*, iterations: int = DEFAULT_KDF_ITERATIONS) -> ShibbolethKdfParams:
    return ShibbolethKdfParams(
        algorithm=KDF_ALGORITHM,
        iterations=iterations,
        salt=base64.urlsafe_b64encode(os.urandom(16)).decode("ascii"),
    )


def derive_fernet_key(passphrase: str, kdf: ShibbolethKdfParams) -> bytes:
    validate_shibboleth(passphrase)
    if kdf.algorithm != KDF_ALGORITHM:
        raise ValueError(f"Unsupported KDF algorithm: {kdf.algorithm}")
    salt = base64.urlsafe_b64decode(kdf.salt.encode("ascii"))
    digest = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=kdf.iterations,
    ).derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(digest)


def verify_against_ciphertext(
    passphrase: str, kdf: ShibbolethKdfParams, ciphertext: str
) -> bool:
    try:
        Fernet(derive_fernet_key(passphrase, kdf)).decrypt(ciphertext.encode("utf-8"))
        return True
    except (InvalidToken, ValueError):
        return False
