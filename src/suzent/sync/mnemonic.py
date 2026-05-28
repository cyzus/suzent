from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_WORDLIST_PATH = Path(__file__).parent / "bip39_english.txt"


def _load_wordlist() -> tuple[str, ...]:
    words = tuple(
        w for w in _WORDLIST_PATH.read_text(encoding="utf-8").splitlines() if w.strip()
    )
    if len(words) != 2048:
        raise RuntimeError(f"BIP39 wordlist must be 2048 words, got {len(words)}")
    return words


_WORDLIST: tuple[str, ...] = _load_wordlist()
_WORD_INDEX: dict[str, int] = {w: i for i, w in enumerate(_WORDLIST)}

# scrypt parameters: N=2^17, r=8, p=1 — ~1s on a modern CPU
_SCRYPT_N = 1 << 17
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32
_SALT_LEN = 32
_NONCE_LEN = 12


def generate_mnemonic(word_count: int = 12) -> str:
    """Generate a random BIP39-compatible mnemonic phrase."""
    if word_count not in (12, 15, 18, 21, 24):
        raise ValueError("word_count must be 12, 15, 18, 21, or 24")
    indices = [secrets.randbelow(2048) for _ in range(word_count)]
    return " ".join(_WORDLIST[i] for i in indices)


def validate_mnemonic(phrase: str) -> list[str]:
    """Return the list of words after validating all are in the BIP39 wordlist."""
    words = phrase.strip().lower().split()
    if len(words) not in (12, 15, 18, 21, 24):
        raise ValueError(
            f"Mnemonic must be 12, 15, 18, 21, or 24 words; got {len(words)}"
        )
    unknown = [w for w in words if w not in _WORD_INDEX]
    if unknown:
        raise ValueError(f"Unknown word(s): {', '.join(unknown)}")
    return words


def derive_key(mnemonic: str, salt: bytes) -> bytes:
    """Derive a 32-byte encryption key from a mnemonic phrase using scrypt."""
    words = validate_mnemonic(mnemonic)
    material = " ".join(words).encode("utf-8")
    kdf = Scrypt(salt=salt, length=_KEY_LEN, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(material)


def new_salt() -> str:
    return base64.urlsafe_b64encode(os.urandom(_SALT_LEN)).decode("ascii")


def encrypt(plaintext: bytes, key: bytes) -> tuple[str, str]:
    """AES-256-GCM encrypt. Returns (ciphertext_b64, nonce_b64)."""
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return (
        base64.urlsafe_b64encode(ct).decode("ascii"),
        base64.urlsafe_b64encode(nonce).decode("ascii"),
    )


def decrypt(ciphertext_b64: str, nonce_b64: str, key: bytes) -> bytes:
    """AES-256-GCM decrypt. Raises ValueError on wrong key."""
    ct = base64.urlsafe_b64decode(ciphertext_b64.encode("ascii"))
    nonce = base64.urlsafe_b64decode(nonce_b64.encode("ascii"))
    try:
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception as exc:
        raise ValueError("Decryption failed: wrong mnemonic or corrupt data") from exc


def mnemonic_fingerprint(mnemonic: str) -> str:
    """4-byte hex fingerprint — shown in UI so users can confirm the phrase matches."""
    words = validate_mnemonic(mnemonic)
    digest = hashlib.sha256(" ".join(words).encode("utf-8")).digest()
    return digest[:4].hex()
