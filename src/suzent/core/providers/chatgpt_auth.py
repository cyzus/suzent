from __future__ import annotations

from typing import Any


class ChatGPTAuthUnavailable(RuntimeError):
    """Raised when LiteLLM's ChatGPT subscription auth surface is unavailable."""


_AUTHENTICATOR_METHODS = (
    "_read_auth_file",
    "_is_token_expired",
    "_request_device_code",
    "_record_device_code_request",
    "_poll_for_authorization_code",
    "_exchange_code_for_tokens",
    "_build_auth_record",
    "_write_auth_file",
    "_refresh_tokens",
    "get_account_id",
)


def _missing_attr_error(name: str) -> ChatGPTAuthUnavailable:
    return ChatGPTAuthUnavailable(
        "LiteLLM ChatGPT subscription authentication is unavailable or changed. "
        f"Missing expected LiteLLM attribute: {name}."
    )


def create_authenticator() -> Any:
    try:
        from litellm.llms.chatgpt.authenticator import Authenticator
    except Exception as exc:
        raise ChatGPTAuthUnavailable(
            "LiteLLM ChatGPT subscription authentication is unavailable."
        ) from exc

    auth = Authenticator()
    for method in _AUTHENTICATOR_METHODS:
        if not hasattr(auth, method):
            raise _missing_attr_error(f"Authenticator.{method}")
    if not hasattr(auth, "auth_file"):
        raise _missing_attr_error("Authenticator.auth_file")
    return auth


def read_auth_file(auth: Any) -> dict[str, Any]:
    data = auth._read_auth_file()
    return data if isinstance(data, dict) else {}


def get_account_id(auth: Any) -> str | None:
    return auth.get_account_id()


def get_valid_access_token(auth: Any, *, refresh: bool = True) -> str | None:
    data = read_auth_file(auth)
    token = data.get("access_token")
    if token and not auth._is_token_expired(data, token):
        return token

    if not refresh:
        return None

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return None

    refreshed = auth._refresh_tokens(refresh_token)
    return refreshed.get("access_token") if isinstance(refreshed, dict) else None


def request_device_code(auth: Any) -> dict[str, Any]:
    device_code = auth._request_device_code()
    auth._record_device_code_request()
    return device_code


def complete_device_login(auth: Any, device_code: dict[str, Any]) -> None:
    auth_code = auth._poll_for_authorization_code(device_code)
    tokens = auth._exchange_code_for_tokens(auth_code)
    auth._write_auth_file(auth._build_auth_record(tokens))


def delete_auth_file(auth: Any) -> None:
    from pathlib import Path

    Path(auth.auth_file).unlink(missing_ok=True)


def chatgpt_api_base() -> str:
    try:
        from litellm.llms.chatgpt.common_utils import CHATGPT_API_BASE
    except Exception as exc:
        raise ChatGPTAuthUnavailable(
            "LiteLLM ChatGPT API base is unavailable."
        ) from exc
    return CHATGPT_API_BASE


def chatgpt_device_verify_url() -> str:
    try:
        from litellm.llms.chatgpt.common_utils import CHATGPT_DEVICE_VERIFY_URL
    except Exception as exc:
        raise ChatGPTAuthUnavailable(
            "LiteLLM ChatGPT device verification URL is unavailable."
        ) from exc
    return CHATGPT_DEVICE_VERIFY_URL


def chatgpt_default_headers(token: str, account_id: str | None) -> dict[str, str]:
    try:
        from litellm.llms.chatgpt.common_utils import get_chatgpt_default_headers
    except Exception as exc:
        raise ChatGPTAuthUnavailable(
            "LiteLLM ChatGPT default headers helper is unavailable."
        ) from exc
    return get_chatgpt_default_headers(token, account_id)


def chatgpt_default_instructions() -> str:
    try:
        from litellm.llms.chatgpt.common_utils import get_chatgpt_default_instructions
    except Exception as exc:
        raise ChatGPTAuthUnavailable(
            "LiteLLM ChatGPT default instructions helper is unavailable."
        ) from exc
    return get_chatgpt_default_instructions()


def get_litellm_httpx_client() -> Any:
    try:
        from litellm.llms.custom_httpx.http_handler import _get_httpx_client
    except Exception as exc:
        raise ChatGPTAuthUnavailable(
            "LiteLLM ChatGPT HTTP client helper is unavailable."
        ) from exc
    return _get_httpx_client()
