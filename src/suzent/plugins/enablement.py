"""Which plugins are on, and which Suzent extras they need.

This module imports nothing from Suzent, so the desktop updater can run it by
path with the environment's Python before that environment has been synced
to the new release:

    python <checkout>/src/suzent/plugins/enablement.py <checkout> <plugins.json>

It prints a JSON list of the extras that ``uv sync`` should install, read from
the checkout's built-in plugin manifests, the user's plugin state and the
checkout's ``config/social.json``. ``PluginManager`` uses the same rules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "plugin.yaml"
# Keys of a chat app's section of social.json that are not credentials.
CHANNEL_SETTING_KEYS = {"enabled", "allowed_users"}


def channel_configured(settings: Any) -> bool:
    """True when a chat app's section of social.json is on and has credentials."""
    if not isinstance(settings, dict) or not settings.get("enabled", True):
        return False
    return any(
        value for key, value in settings.items() if key not in CHANNEL_SETTING_KEYS
    )


def is_enabled(
    plugin_id: str,
    *,
    builtin: bool,
    channel: str | None,
    default_enabled: bool,
    state: dict[str, dict[str, Any]],
    social: dict[str, Any],
) -> bool:
    """Whether a plugin is on: the user's choice, else the built-in default."""
    if plugin_id in state:
        return bool(state[plugin_id].get("enabled"))
    # Only plugins shipped with Suzent may switch themselves on.
    if not builtin:
        return False
    if channel:
        # A chat app the user already set up keeps working after the
        # upgrade that split it into its own plugin.
        return channel_configured(social.get(channel))
    return default_enabled


def read_json_dict(path: Path | None) -> dict[str, Any]:
    """A JSON object from ``path``; empty when missing or unreadable."""
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_state(path: Path) -> dict[str, dict[str, Any]]:
    """Per-plugin entries of the user's ``plugins.json``."""
    plugins = read_json_dict(path).get("plugins")
    if not isinstance(plugins, dict):
        return {}
    return {str(k): v for k, v in plugins.items() if isinstance(v, dict)}


def user_social_file(
    checkout: Path, state_file: Path, social_file: Path | None = None
) -> Path:
    """The user's social.json: the data-dir copy beside ``plugins.json`` wins;
    else ``social_file`` (an older installer's pick); else the checkout's,
    where versions before the data-dir move kept it."""
    candidates = [Path(state_file).expanduser().parent / "social.json"]
    if social_file is not None:
        candidates.append(Path(social_file))
    candidates.append(checkout / "config" / "social.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def builtin_plugin_extras(
    checkout: Path, state_file: Path, social_file: Path | None = None
) -> list[str]:
    """Extras of the enabled built-in plugins of ``checkout``.

    Only built-in plugins can name Suzent extras; third-party plugins keep
    their packages in their own directory, outside the synced environment.
    A checkout from before plugins existed gets ``social``, as it always did.
    The user's chat-app configuration is found by :func:`user_social_file`;
    ``social_file`` is a fallback for a live installation that still keeps it
    in its checkout (a clean checkout of a new release has none).
    """
    import yaml

    builtin_dir = checkout / "plugins"
    if not builtin_dir.is_dir():
        return ["social"]
    # Callers pass SUZENT_DATA_DIR verbatim (e.g. "~/custom" from a shell);
    # expand it as get_data_dir() does, so the real plugin state is read.
    state_file = Path(state_file).expanduser()
    state = read_state(state_file)
    social = read_json_dict(user_social_file(checkout, state_file, social_file))
    extras: dict[str, None] = {}
    for manifest_path in sorted(builtin_dir.glob(f"*/{MANIFEST_FILENAME}")):
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(manifest, dict) or not manifest.get("id"):
            continue
        if is_enabled(
            str(manifest["id"]),
            builtin=True,
            channel=manifest.get("channel"),
            default_enabled=bool(manifest.get("default_enabled", False)),
            state=state,
            social=social,
        ):
            extras.update(dict.fromkeys(str(e) for e in manifest.get("extras") or []))
    return list(extras)


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(
            "usage: enablement.py <checkout> <plugins.json> [social.json]",
            file=sys.stderr,
        )
        return 2
    social = Path(argv[2]) if len(argv) == 3 else None
    print(json.dumps(builtin_plugin_extras(Path(argv[0]), Path(argv[1]), social)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
