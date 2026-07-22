from suzent.sync.shibboleth import (
    derive_fernet_key,
    new_kdf_params,
    verify_against_ciphertext,
)


def test_derive_key_is_deterministic_for_same_passphrase_and_salt():
    kdf = new_kdf_params()
    first = derive_fernet_key("repeatable-shibboleth", kdf)
    second = derive_fernet_key("repeatable-shibboleth", kdf)
    assert first == second


def test_verify_against_ciphertext():
    from cryptography.fernet import Fernet

    kdf = new_kdf_params()
    phrase = "verify-shibboleth"
    key = derive_fernet_key(phrase, kdf)
    token = Fernet(key).encrypt(b"secret").decode("utf-8")
    assert verify_against_ciphertext(phrase, kdf, token)
    assert not verify_against_ciphertext("wrong-shibboleth", kdf, token)
