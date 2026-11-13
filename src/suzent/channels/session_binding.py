"""Which session a chat-app conversation talks to, kept across restarts.

A binding is keyed by who is talking: ``platform:sender_id`` for one account,
or the shared direct-message key when direct messages from every chat app go
to Regent, so a switch made on one app holds on the others too.
"""

import json
import threading
from pathlib import Path

from suzent.config.paths import get_data_dir
from suzent.logger import get_logger

logger = get_logger(__name__)

SHARED_DIRECT_KEY = "direct"
_FILENAME = "social_sessions.json"
_lock = threading.Lock()


def sender_key(platform: str, sender_id: str) -> str:
    return f"{platform}:{sender_id}"


def _path() -> Path:
    return get_data_dir() / _FILENAME


def _load() -> dict[str, str]:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not read chat-app session bindings: {}", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _save(bindings: dict[str, str]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(bindings, indent=2), encoding="utf-8")
    tmp.replace(path)


def get_binding(key: str) -> str | None:
    with _lock:
        return _load().get(key)


def set_binding(key: str, chat_id: str) -> None:
    with _lock:
        bindings = _load()
        bindings[key] = chat_id
        _save(bindings)


def clear_binding(key: str) -> None:
    with _lock:
        bindings = _load()
        if bindings.pop(key, None) is not None:
            _save(bindings)
