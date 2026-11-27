"""Validated configuration and command boundary for managed browsing."""

import os
import re
import tempfile
from threading import Lock
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from suzent.config.paths import DATA_DIR, USER_CONFIG_DIR

_PREFERENCES_LOCK = Lock()
MAX_SCRIPT_CHARS = 20_000
MAX_BATCH_STEPS = 20


def normalize_browser_url(value: str) -> str:
    """Allow web navigation and an explicit empty page."""
    value = value.strip()
    if value == "about:blank":
        return value
    if not value or any(char.isspace() for char in value):
        raise ValueError("open requires a non-empty HTTP(S) URL")
    if "://" not in value:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) and not re.match(
            r"^[^/:]+:\d+(?:/|$)", value
        ):
            raise ValueError("Only HTTP(S) URLs and about:blank are supported")
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) URLs and about:blank are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs must not contain credentials")
    _ = parsed.port
    return value


def site_origin(value: str) -> str:
    """The origin a site permission is kept under, as ``location.origin`` spells it."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("site must be an http(s) origin, e.g. https://example.com")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("site must not contain credentials")
    try:
        host = parsed.hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("site has an invalid host name") from exc
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    default = 443 if parsed.scheme == "https" else 80
    return f"{parsed.scheme}://{host}" + (
        f":{port}" if port and port != default else ""
    )


class BrowserPreferences(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    persistent: bool = False
    # The built-in browser keeps its own sign-ins by default, apart from the
    # managed browser's profile above.
    desktop_persistent: bool = True
    headless: bool = True
    channel: Literal["chromium", "chrome", "msedge"] = "chromium"
    # "desktop" uses the Suzent app's built-in browser while the app is open
    # and falls back to "managed" when it is not (web UI, headless service).
    connection_mode: Literal["desktop", "managed", "existing", "extension"] = "desktop"

    @classmethod
    def load(cls) -> Self:
        path = USER_CONFIG_DIR / "browser.json"
        return (
            cls.model_validate_json(path.read_text(encoding="utf-8"))
            if path.exists()
            else cls()
        )

    def save_changes(self) -> None:
        """Merge only submitted fields with stored preferences, before overrides."""
        with _PREFERENCES_LOCK:
            values = BrowserPreferences.load().model_dump()
            values.update(self.model_dump(exclude_unset=True))
            BrowserPreferences.model_validate(values).save()

    def save(self) -> None:
        path = USER_CONFIG_DIR / "browser.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(self.model_dump_json(indent=2))
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class BrowserSettings(BrowserPreferences):
    model_config = ConfigDict(strict=False, extra="forbid")

    profile_dir: Path = Field(default_factory=lambda: DATA_DIR / "browser_profile")

    @classmethod
    def load(cls) -> Self:
        saved = BrowserPreferences.load()
        values = saved.model_dump()
        values.update(
            {
                key: os.environ[f"SUZENT_BROWSER_{key.upper()}"]
                for key in cls.model_fields
                if f"SUZENT_BROWSER_{key.upper()}" in os.environ
            }
        )
        return cls.model_validate(values)

    @classmethod
    def from_environment(cls) -> Self:
        values = {
            key: os.environ[f"SUZENT_BROWSER_{key.upper()}"]
            for key in cls.model_fields
            if f"SUZENT_BROWSER_{key.upper()}" in os.environ
        }
        return cls.model_validate(values)


class BrowserCommand(BaseModel):
    model_config = ConfigDict(strict=True)

    command: Literal[
        "open",
        "snapshot",
        "click",
        "dblclick",
        "hover",
        "fill",
        "type",
        "press",
        "back",
        "forward",
        "reload",
        "refresh",
        "click_coords",
        "scroll",
        "tabs",
        "select_tab",
        "new_tab",
        "close_tab",
        "run_js",
        "batch",
    ]
    arguments: list[str] = Field(default_factory=list)
    site: str | None = None

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        args = self.arguments
        match self.command:
            case "select_tab" | "close_tab":
                if len(args) != 1 or not re.fullmatch(r"tab-\d+", args[0]):
                    raise ValueError(f"{self.command} expects [tab-id] from tabs")
            case "new_tab":
                if len(args) > 1:
                    raise ValueError("new_tab expects [url] or [] for a blank tab")
                self.arguments = [
                    normalize_browser_url(args[0] if args else "about:blank")
                ]
            case "open":
                if len(args) > 1:
                    raise ValueError("open expects [url] or [] for about:blank")
                self.arguments = [
                    normalize_browser_url(args[0] if args else "about:blank")
                ]
            case "click" | "dblclick" | "hover" | "fill" | "type" | "press":
                count = 1 if self.command in {"click", "dblclick", "hover"} else 2
                syntax = "[ref]" if count == 1 else "[ref, value]"
                if len(args) != count:
                    raise ValueError(f"{self.command} expects {syntax}")
                if not re.fullmatch(r"@g\d+e\d+", args[0]):
                    raise ValueError(
                        "Use an exact ref from the latest snapshot, e.g. @g1e0"
                    )
                if self.command == "press" and not args[1]:
                    raise ValueError("press requires a non-empty key")
            case "click_coords" | "scroll":
                if self.command == "scroll" and not args:
                    self.arguments = ["0", "500"]
                elif len(args) != 2 or any(
                    not re.fullmatch(r"-?\d{1,6}", arg) for arg in args
                ):
                    raise ValueError(f"{self.command} expects two integer arguments")
                if self.command == "click_coords" and any(int(arg) < 0 for arg in args):
                    raise ValueError("click_coords requires non-negative coordinates")
            case "snapshot":
                if args == ["-i"]:
                    self.arguments = []
                elif len(args) > 2:
                    raise ValueError("snapshot expects [] or [offset, limit]")
                elif args:
                    if any(not re.fullmatch(r"\d{1,8}", arg) for arg in args):
                        raise ValueError("snapshot offset and limit must be integers")
                    if len(args) == 2 and not 1 <= int(args[1]) <= 100:
                        raise ValueError("snapshot limit must be between 1 and 100")
            case "run_js":
                if len(args) != 1 or not args[0].strip():
                    raise ValueError("run_js expects [code]")
                if len(args[0]) > MAX_SCRIPT_CHARS:
                    raise ValueError(
                        f"run_js code must be at most {MAX_SCRIPT_CHARS} characters"
                    )
                if self.site is None:
                    raise ValueError(
                        "run_js needs site, the origin of the page, e.g. https://example.com"
                    )
                origin = site_origin(self.site)
                if origin != self.site:
                    raise ValueError(f"site must be the page's origin: {origin}")
            case "batch":
                if not 1 <= len(args) <= MAX_BATCH_STEPS:
                    raise ValueError(
                        f"batch expects 1 to {MAX_BATCH_STEPS} steps, e.g. ['fill @g1e2 hello', 'click @g1e3']"
                    )
            case _:
                if args:
                    raise ValueError(f"{self.command} expects no arguments")
        return self
