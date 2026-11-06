"""Map a desktop tool call onto an agent-desktop 1.0.x argv list.

Flag names and required arguments follow the CLI reference (JSON envelope 2.5).
Nothing here starts a process.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

DesktopCommand = Literal[
    "snapshot",
    "find",
    "get",
    "is",
    "screenshot",
    "list-apps",
    "list-windows",
    "list-displays",
    "list-surfaces",
    "list-notifications",
    "clipboard-get",
    "status",
    "permissions",
    "version",
    "skills",
    "session",
    "wait",
    "click",
    "double-click",
    "triple-click",
    "right-click",
    "type",
    "set-value",
    "clear",
    "focus",
    "select",
    "toggle",
    "check",
    "uncheck",
    "expand",
    "collapse",
    "scroll",
    "scroll-to",
    "press",
    "hover",
    "drag",
    "mouse-move",
    "mouse-click",
    "mouse-wheel",
    "key-down",
    "key-up",
    "mouse-down",
    "mouse-up",
    "launch",
    "close-app",
    "focus-window",
    "resize-window",
    "move-window",
    "minimize",
    "maximize",
    "restore",
    "open-system-surface",
    "dismiss-notification",
    "dismiss-all-notifications",
    "notification-action",
    "clipboard-set",
    "clipboard-clear",
    "batch",
]

DESKTOP_COMMANDS: frozenset[str] = frozenset(get_args(DesktopCommand))

# These names exist so a caller gets the CLI's reason, but the CLI refuses
# them until a daemon can release a held key or button. Rejecting them here
# keeps that refusal from looking like an action the user should approve.
HELD_INPUT: frozenset[str] = frozenset({"key-down", "key-up", "mouse-down", "mouse-up"})

READONLY_COMMANDS: frozenset[str] = frozenset(
    {
        "snapshot",
        "find",
        "get",
        "is",
        "screenshot",
        "list-apps",
        "list-windows",
        "list-displays",
        "list-surfaces",
        "list-notifications",
        "clipboard-get",
        "status",
        "permissions",
        "version",
        "skills",
        "session",
        "wait",
    }
)

_REF = re.compile(r"^@[A-Za-z0-9]+:e[0-9]+$")
_SESSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_XY = re.compile(r"^-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_STATE_TOKENS = frozenset(
    {
        "focused",
        "disabled",
        "secure",
        "expanded",
        "checked",
        "selected",
        "hidden",
        "busy",
        "modal",
        "required",
        "indeterminate",
        "pressed",
        "readonly",
        "offscreen",
        "invalid",
        "multiselectable",
        "haspopup",
    }
)
_GET_PROPERTIES = frozenset({"text", "value", "title", "bounds", "role", "states"})
_IS_PROPERTIES = frozenset(
    {"visible", "enabled", "checked", "focused", "expanded", "selected"}
)
_SHELL_SURFACES = frozenset(
    {
        "start-menu",
        "taskbar",
        "system-tray",
        "system-tray-overflow",
        "action-center",
    }
)
_MODIFIERS = frozenset({"shift", "meta", "ctrl", "alt"})
_SKILL_ACTIONS = frozenset({"list", "get", "path"})
_SESSION_ACTIONS = frozenset({"start", "end", "list", "gc"})
_BATCH_MUTATING_FLAGS = frozenset({"request", "guide"})

_WAIT = {"wait_for", "wait_for_gone", "wait_timeout_ms"}
_TARGET = {"app", "window_id"}
_REF_TIMEOUT = {"ref", "timeout_ms"} | _WAIT

_COMMAND_FIELDS: dict[str, set[str]] = {
    "snapshot": _TARGET
    | _WAIT
    | {
        "timeout_ms",
        "interactive_only",
        "compact",
        "skeleton",
        "include_bounds",
        "force_electron_a11y",
        "root",
        "surface",
        "max_depth",
    },
    "find": _TARGET
    | {
        "timeout_ms",
        "role",
        "name",
        "value",
        "text",
        "description",
        "native_id",
        "exact",
        "states",
        "root",
        "surface",
        "find_count",
        "find_first",
        "find_last",
        "nth",
        "limit",
    },
    "get": {"ref", "property"},
    "is": {"ref", "property"},
    "screenshot": {"path", "app", "window_id", "screen"},
    "list-apps": {"app", "timeout_ms"},
    "list-windows": {"app", "timeout_ms"},
    "list-displays": set(),
    "list-surfaces": {"app"},
    "list-notifications": {"app", "text", "limit"},
    "clipboard-get": {"clipboard_format", "path"},
    "clipboard-set": {"text", "image", "file_urls"},
    "clipboard-clear": set(),
    "status": set(),
    "permissions": {"request_permissions", "guide"},
    "version": set(),
    "skills": {"subcommand", "skill", "reference", "full"},
    "session": {
        "subcommand",
        "label",
        "no_trace",
        "screenshots",
        "cursor",
        "multi_agent",
        "session_id",
        "older_than",
        "ended",
    },
    "wait": {
        "ms",
        "element",
        "predicate",
        "value",
        "action_name",
        "window_title",
        "text",
        "text_count",
        "app",
        "menu",
        "menu_closed",
        "notification",
        "event",
        "window_id",
        "timeout_ms",
    },
    "click": set(_REF_TIMEOUT),
    "double-click": set(_REF_TIMEOUT),
    "triple-click": set(_REF_TIMEOUT),
    "right-click": set(_REF_TIMEOUT),
    "type": _REF_TIMEOUT | {"text", "interval_ms"},
    "set-value": _REF_TIMEOUT | {"value"},
    "clear": set(_REF_TIMEOUT),
    "focus": set(_REF_TIMEOUT),
    "select": _REF_TIMEOUT | {"value"},
    "toggle": set(_REF_TIMEOUT),
    "check": set(_REF_TIMEOUT),
    "uncheck": set(_REF_TIMEOUT),
    "expand": set(_REF_TIMEOUT),
    "collapse": set(_REF_TIMEOUT),
    "scroll": _REF_TIMEOUT | {"direction", "amount"},
    "scroll-to": set(_REF_TIMEOUT),
    "press": _WAIT | {"combo", "app", "window_id", "force"},
    "hover": _WAIT | {"ref", "xy", "timeout_ms"},
    "drag": _WAIT
    | {
        "from_ref",
        "from_xy",
        "to_ref",
        "to_xy",
        "duration_ms",
        "drop_delay_ms",
        "timeout_ms",
        "wait_for_scope",
    },
    "mouse-move": {"xy"},
    "mouse-click": {"xy", "button", "count", "modifiers"},
    "mouse-wheel": {"x", "y", "dx", "dy", "modifiers"},
    "launch": {
        "app",
        "timeout_ms",
        "launch_args",
        "env",
        "cwd",
        "no_attach",
        "activate",
    },
    "close-app": {"app", "force"},
    "focus-window": {"window_id", "app", "title"},
    "resize-window": {"width", "height", "app", "window_id"},
    "move-window": {"x", "y", "app", "window_id"},
    "minimize": set(_TARGET),
    "maximize": set(_TARGET),
    "restore": set(_TARGET),
    "open-system-surface": {"surface"},
    "dismiss-notification": {"index", "expected_app", "expected_title", "app"},
    "dismiss-all-notifications": {"app"},
    "notification-action": {
        "index",
        "action_name",
        "expected_app",
        "expected_title",
        "app",
    },
    "batch": {"entries", "stop_on_error", "timeout_ms"},
}


class DesktopOptions(BaseModel):
    """Flags for one agent-desktop command.

    Names match the CLI. ``subcommand`` is the ``skills`` or ``session``
    subcommand. Batch ``entries`` use the CLI's own shape, ``{command, args}``,
    with hyphenated flags written as underscores (``window_id``).
    """

    model_config = ConfigDict(extra="forbid")

    app: str | None = None
    window_id: str | None = None
    ref: str | None = Field(
        default=None,
        description="Qualified ref @<snapshot_id>:e<N> from snapshot or find. A bare @eN is rejected.",
    )
    text: str | None = None
    value: str | None = None
    title: str | None = None
    window_title: str | None = Field(
        default=None,
        description="wait --window title substring. With event, it narrows that event instead.",
    )
    role: str | None = None
    name: str | None = None
    description: str | None = None
    native_id: str | None = None
    exact: bool = False
    states: list[str] | None = None
    root: str | None = None
    surface: str | None = None
    interactive_only: bool = False
    compact: bool = False
    skeleton: bool = False
    include_bounds: bool = False
    force_electron_a11y: bool = False
    max_depth: int | None = None
    find_count: bool = False
    find_first: bool = False
    find_last: bool = False
    nth: int | None = None
    limit: int | None = None
    property: str | None = None
    timeout_ms: int | None = None
    interval_ms: int | None = None
    direction: Literal["up", "down", "left", "right"] | None = None
    amount: int | None = None
    combo: str | None = None
    force: bool = False
    launch_args: list[str] | None = Field(
        default=None, description="Repeated launch --arg values, in order."
    )
    env: list[str] | None = Field(
        default=None, description="launch --env KEY=VALUE entries."
    )
    cwd: str | None = None
    no_attach: bool = False
    activate: bool = False
    width: float | None = None
    height: float | None = None
    x: float | None = None
    y: float | None = None
    path: str | None = Field(
        default=None,
        description="screenshot output path, or clipboard-get --out. Writing a path is not read-only.",
    )
    screen: int | None = None
    clipboard_format: Literal["text", "auto", "image", "file-urls"] | None = None
    image: str | None = None
    file_urls: list[str] | None = None
    request_permissions: bool = Field(
        default=False,
        description="permissions --request. Prompts the OS. Not read-only.",
    )
    guide: bool = Field(
        default=False,
        description="permissions --guide. Opens the macOS Accessibility guide. Not read-only.",
    )
    subcommand: str | None = Field(
        default=None,
        description="skills: list, get, or path. session: start, end, list, or gc.",
    )
    skill: str | None = None
    reference: str | None = None
    full: bool = False
    label: str | None = None
    no_trace: bool = False
    screenshots: bool = False
    cursor: bool = False
    multi_agent: bool = False
    older_than: int | None = None
    ended: bool = False
    session_id: str | None = None
    entries: list[dict[str, Any]] | None = Field(
        default=None,
        description="batch entries: {command, args?, session?}. args use CLI underscore names.",
    )
    stop_on_error: bool = False
    xy: str | None = Field(
        default=None, description="Absolute x,y. Negative values are passed as --xy=."
    )
    from_ref: str | None = None
    to_ref: str | None = None
    from_xy: str | None = None
    to_xy: str | None = None
    duration_ms: int | None = None
    drop_delay_ms: int | None = None
    wait_for_scope: Literal["to", "from"] | None = None
    button: Literal["left", "right", "middle"] | None = None
    count: int | None = None
    modifiers: list[str] | None = None
    dx: float | None = None
    dy: float | None = None
    expected_app: str | None = None
    expected_title: str | None = None
    index: int | None = None
    action_name: str | None = None
    ms: int | None = None
    element: str | None = None
    predicate: Literal["exists", "enabled", "visible", "actionable", "value"] | None = (
        None
    )
    text_count: int | None = None
    menu: bool = False
    menu_closed: bool = False
    notification: bool = False
    event: (
        Literal[
            "window-opened",
            "window-closed",
            "app-launched",
            "app-terminated",
            "focus-changed",
            "surface-appeared",
            "surface-dismissed",
        ]
        | None
    ) = None
    wait_for: str | None = None
    wait_for_gone: str | None = None
    wait_timeout_ms: int | None = None


@dataclass(frozen=True)
class PreparedCall:
    argv: list[str]
    readonly: bool
    command: str
    timeout_seconds: float


def prepare_from_tool_args(args: dict[str, Any] | None) -> PreparedCall:
    """Build argv from the argument object the permission engine sees."""
    payload = args or {}
    command = payload.get("command")
    if not isinstance(command, str):
        raise ValueError("command must be the agent-desktop command name")
    options = payload.get("options")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("options must be an object")
    headed = payload.get("headed", False)
    if not isinstance(headed, bool):
        raise ValueError("headed must be a boolean")
    session = payload.get("session")
    if session is not None and not isinstance(session, str):
        raise ValueError("session must be a string")
    return prepare_call(command, options, headed=headed, session=session)


def is_readonly_desktop_args(args: dict[str, Any] | None) -> bool:
    """True when the call only reads desktop state. Invalid calls are not reads."""
    try:
        return prepare_from_tool_args(args).readonly
    except ValueError:
        return False


def prepare_call(
    command: str,
    options: DesktopOptions | dict[str, Any] | None = None,
    *,
    headed: bool = False,
    session: str | None = None,
) -> PreparedCall:
    """Validate one call and return the argv the host process should exec."""
    if not isinstance(headed, bool):
        raise ValueError("headed must be a boolean")
    name = command.strip()
    if name not in DESKTOP_COMMANDS:
        supported = ", ".join(sorted(DESKTOP_COMMANDS))
        raise ValueError(
            f"Unknown desktop command {command!r}. Supported: {supported}."
        )
    if name in HELD_INPUT:
        raise ValueError(
            f"{name} is refused by agent-desktop until a daemon can release a held "
            "input. Use press for a key combo, and mouse-click or drag for the pointer."
        )
    parsed = options if isinstance(options, DesktopOptions) else _parse_options(options)
    _reject_unused(name, parsed)
    session_id = _optional_session(session)
    flags: list[str] = []
    positionals: list[str] = []
    _append_command(name, parsed, flags, positionals)
    argv: list[str] = []
    if headed:
        argv.append("--headed")
    if session_id:
        argv.extend(["--session", session_id])
    argv.append(name)
    argv.extend(flags)
    if any(item.startswith("-") for item in positionals):
        argv.append("--")
    argv.extend(positionals)
    return PreparedCall(
        argv=argv,
        readonly=_readonly(name, parsed, headed),
        command=name,
        timeout_seconds=_timeout_seconds(name, parsed),
    )


def _parse_options(raw: dict[str, Any] | None) -> DesktopOptions:
    if not raw:
        return DesktopOptions()
    cleaned = {key: value for key, value in raw.items() if value is not None}
    try:
        return DesktopOptions.model_validate(cleaned)
    except ValidationError as exc:
        details = "; ".join(error["msg"] for error in exc.errors(include_input=False))
        raise ValueError(details) from exc


def _reject_unused(command: str, options: DesktopOptions) -> None:
    unused = set(options.model_dump(exclude_defaults=True)) - _COMMAND_FIELDS[command]
    if unused:
        names = ", ".join(sorted(unused))
        raise ValueError(f"{command} does not use: {names}")


def _readonly(command: str, options: DesktopOptions, headed: bool) -> bool:
    if command == "batch":
        return _batch_readonly(options.entries or [], headed=headed)
    if command not in READONLY_COMMANDS:
        return False
    if command == "permissions" and (options.request_permissions or options.guide):
        return False
    if command == "session":
        return options.subcommand == "list"
    if command == "screenshot" and options.path:
        return False
    if command == "clipboard-get" and options.path:
        return False
    if command == "list-notifications" and headed:
        return False
    return True


def _batch_readonly(entries: list[dict[str, Any]], *, headed: bool) -> bool:
    for entry in entries:
        name = str(entry.get("command") or "")
        if name not in READONLY_COMMANDS:
            return False
        args = entry.get("args") if isinstance(entry.get("args"), dict) else {}
        if name == "permissions" and any(
            args.get(flag) for flag in _BATCH_MUTATING_FLAGS
        ):
            return False
        if name == "session" and args.get("action") != "list":
            return False
        if name in {"screenshot", "clipboard-get"} and args.get("path"):
            return False
        if name == "list-notifications" and headed:
            return False
        action = args.get("action")
        if name == "skills" and action not in (None, "list", "get", "path"):
            return False
    return True


def _timeout_seconds(command: str, options: DesktopOptions) -> float:
    milliseconds = 30_000
    if command == "batch":
        milliseconds = options.timeout_ms if options.timeout_ms is not None else 60_000
    elif command == "wait" and options.ms is not None:
        milliseconds = options.ms
    elif options.timeout_ms is not None:
        milliseconds = options.timeout_ms
    if options.wait_timeout_ms is not None:
        milliseconds = max(milliseconds, options.wait_timeout_ms)
    return min(milliseconds / 1000 + 15, 180)


def _append_command(
    command: str,
    options: DesktopOptions,
    flags: list[str],
    positionals: list[str],
) -> None:
    match command:
        case "snapshot":
            _app_window(flags, options)
            _mark(flags, "--interactive-only", options.interactive_only)
            _mark(flags, "--compact", options.compact)
            _mark(flags, "--skeleton", options.skeleton)
            _mark(flags, "--include-bounds", options.include_bounds)
            _mark(flags, "--force-electron-a11y", options.force_electron_a11y)
            if options.root and options.surface:
                raise ValueError("snapshot root cannot be combined with surface")
            if options.root:
                _opt(flags, "--root", _ref(options.root, "root"))
            if options.surface:
                _opt(flags, "--surface", _surface_token(options.surface))
            if options.max_depth is not None:
                depth = _bounded_int(options.max_depth, "max_depth", 1, 50)
                _opt(flags, "--max-depth", str(depth))
            _timeout_flag(flags, options)
            _wait_flags(flags, options, command)
        case "find":
            _find(flags, options)
        case "get" | "is":
            positionals.append(_require_ref(options))
            if options.property:
                allowed = _GET_PROPERTIES if command == "get" else _IS_PROPERTIES
                if options.property not in allowed:
                    choices = ", ".join(sorted(allowed))
                    raise ValueError(f"{command} property must be one of: {choices}")
                _opt(flags, "--property", options.property)
        case "screenshot":
            if options.screen is not None and (options.app or options.window_id):
                raise ValueError(
                    "screenshot --screen cannot be combined with an app or window"
                )
            if options.path:
                positionals.append(_path(options.path, "path"))
            _app_window(flags, options)
            if options.screen is not None:
                _opt(
                    flags,
                    "--screen",
                    str(_bounded_int(options.screen, "screen", 0, 64)),
                )
        case "list-apps" | "list-windows":
            if options.app:
                _opt(flags, "--app", _line(options.app, "app"))
            _timeout_flag(flags, options)
        case "list-displays" | "status" | "version" | "clipboard-clear":
            return
        case "list-surfaces":
            if options.app:
                _opt(flags, "--app", _line(options.app, "app"))
        case "list-notifications":
            if options.app:
                _opt(flags, "--app", _line(options.app, "app"))
            if options.text:
                _opt(flags, "--text", _line(options.text, "text"))
            if options.limit is not None:
                _opt(
                    flags, "--limit", str(_bounded_int(options.limit, "limit", 1, 500))
                )
        case "clipboard-get":
            if options.clipboard_format:
                _opt(flags, "--format", options.clipboard_format)
            if options.path:
                _opt(flags, "--out", _path(options.path, "path"))
        case "clipboard-set":
            _clipboard_set(flags, positionals, options)
        case "permissions":
            _mark(flags, "--request", options.request_permissions)
            _mark(flags, "--guide", options.guide)
        case "skills":
            _skills(flags, positionals, options)
        case "session":
            _session(flags, positionals, options)
        case "wait":
            _wait(flags, positionals, options)
        case (
            "click"
            | "double-click"
            | "triple-click"
            | "right-click"
            | "clear"
            | "focus"
            | "toggle"
            | "check"
            | "uncheck"
            | "expand"
            | "collapse"
            | "scroll-to"
        ):
            positionals.append(_require_ref(options))
            _timeout_flag(flags, options)
            _wait_flags(flags, options, command)
        case "type":
            positionals.append(_require_ref(options))
            if options.text is None:
                raise ValueError("type requires options.text")
            positionals.append(_text(options.text, "text"))
            if options.interval_ms is not None:
                _opt(
                    flags,
                    "--interval-ms",
                    str(_bounded_int(options.interval_ms, "interval_ms", 1, 2000)),
                )
            _timeout_flag(flags, options)
            _wait_flags(flags, options, command)
        case "set-value" | "select":
            positionals.append(_require_ref(options))
            if options.value is None:
                raise ValueError(f"{command} requires options.value")
            positionals.append(_text(options.value, "value"))
            _timeout_flag(flags, options)
            _wait_flags(flags, options, command)
        case "scroll":
            positionals.append(_require_ref(options))
            if options.direction:
                _opt(flags, "--direction", options.direction)
            if options.amount is not None:
                _opt(
                    flags,
                    "--amount",
                    str(_bounded_int(options.amount, "amount", 1, 1000)),
                )
            _timeout_flag(flags, options)
            _wait_flags(flags, options, command)
        case "press":
            if not options.combo:
                raise ValueError(
                    "press requires options.combo, such as return or ctrl+s"
                )
            positionals.append(_line(options.combo, "combo"))
            _app_window(flags, options)
            _mark(flags, "--force", options.force)
            _wait_flags(flags, options, command)
        case "hover":
            _hover(flags, positionals, options)
            _wait_flags(flags, options, command)
        case "drag":
            _drag(flags, options)
            _wait_flags(flags, options, command)
        case "mouse-move":
            if not options.xy:
                raise ValueError("mouse-move requires options.xy as x,y")
            _opt(flags, "--xy", _xy(options.xy))
        case "mouse-click":
            if not options.xy:
                raise ValueError("mouse-click requires options.xy as x,y")
            _opt(flags, "--xy", _xy(options.xy))
            if options.button:
                _opt(flags, "--button", options.button)
            if options.count is not None:
                _opt(
                    flags, "--count", str(_bounded_int(options.count, "count", 1, 100))
                )
            _modifiers(flags, options)
        case "mouse-wheel":
            if options.x is None or options.y is None:
                raise ValueError("mouse-wheel requires options.x and options.y")
            _opt(flags, "--x", _number(options.x, "x"))
            _opt(flags, "--y", _number(options.y, "y"))
            if options.dx is not None:
                _opt(flags, "--dx", _number(options.dx, "dx"))
            if options.dy is not None:
                _opt(flags, "--dy", _number(options.dy, "dy"))
            _modifiers(flags, options)
        case "launch":
            if not options.app:
                raise ValueError("launch requires options.app")
            positionals.append(_line(options.app, "app"))
            _timeout_flag(flags, options)
            for arg in options.launch_args or []:
                _opt(flags, "--arg", _line(arg, "launch_args"))
            for item in options.env or []:
                if not _ENV.fullmatch(item) or "\n" in item or "\r" in item:
                    raise ValueError("env entries must be KEY=VALUE on one line")
                _opt(flags, "--env", item)
            if options.cwd:
                _opt(flags, "--cwd", _path(options.cwd, "cwd"))
            _mark(flags, "--no-attach", options.no_attach)
            _mark(flags, "--activate", options.activate)
        case "close-app":
            if not options.app:
                raise ValueError("close-app requires options.app")
            positionals.append(_line(options.app, "app"))
            _mark(flags, "--force", options.force)
        case "focus-window":
            if not (options.window_id or options.app or options.title):
                raise ValueError(
                    "focus-window requires options.window_id, app, or title"
                )
            _app_window(flags, options)
            if options.title:
                _opt(flags, "--title", _line(options.title, "title"))
        case "resize-window":
            if options.width is None or options.height is None:
                raise ValueError(
                    "resize-window requires options.width and options.height"
                )
            _opt(flags, "--width", _positive_number(options.width, "width"))
            _opt(flags, "--height", _positive_number(options.height, "height"))
            _app_window(flags, options)
        case "move-window":
            if options.x is None or options.y is None:
                raise ValueError("move-window requires options.x and options.y")
            _opt(flags, "--x", _number(options.x, "x"))
            _opt(flags, "--y", _number(options.y, "y"))
            _app_window(flags, options)
        case "minimize" | "maximize" | "restore":
            _app_window(flags, options)
        case "open-system-surface":
            if options.surface not in _SHELL_SURFACES:
                choices = ", ".join(sorted(_SHELL_SURFACES))
                raise ValueError(
                    f"open-system-surface surface must be one of: {choices}"
                )
            _opt(flags, "--surface", options.surface)
        case "dismiss-notification":
            _notification_index(positionals, options)
            _expected(flags, options)
            if options.app:
                _opt(flags, "--app", _line(options.app, "app"))
        case "dismiss-all-notifications":
            if options.app:
                _opt(flags, "--app", _line(options.app, "app"))
        case "notification-action":
            _notification_index(positionals, options)
            if not options.action_name:
                raise ValueError("notification-action requires options.action_name")
            positionals.append(_line(options.action_name, "action_name"))
            _expected(flags, options)
            if options.app:
                _opt(flags, "--app", _line(options.app, "app"))
        case "batch":
            _batch(flags, positionals, options)
        case _:
            raise ValueError(f"Unknown desktop command {command!r}.")


def _find(flags: list[str], options: DesktopOptions) -> None:
    picks = [
        name
        for name, enabled in (
            ("find_count", options.find_count),
            ("find_first", options.find_first),
            ("find_last", options.find_last),
            ("nth", options.nth is not None),
            ("limit", options.limit is not None),
        )
        if enabled
    ]
    if len(picks) > 1:
        raise ValueError(
            "find accepts only one of find_count, find_first, find_last, nth, or limit"
        )
    _app_window(flags, options)
    if options.role:
        _opt(flags, "--role", _line(options.role, "role"))
    if options.name:
        _opt(flags, "--name", _line(options.name, "name"))
    if options.value:
        _opt(flags, "--value", _line(options.value, "value"))
    if options.text:
        _opt(flags, "--text", _line(options.text, "text"))
    if options.description:
        _opt(flags, "--description", _line(options.description, "description"))
    if options.native_id:
        _opt(flags, "--native-id", _line(options.native_id, "native_id"))
    _mark(flags, "--exact", options.exact)
    for state in options.states or []:
        _opt(flags, "--state", _state(state))
    if options.root:
        _opt(flags, "--root", _ref(options.root, "root"))
    if options.surface:
        _opt(flags, "--surface", _surface_token(options.surface))
    if options.root and options.surface:
        raise ValueError("find --root cannot be combined with --surface")
    _timeout_flag(flags, options)
    if options.find_count:
        flags.append("--count")
    if options.find_first:
        flags.append("--first")
    if options.find_last:
        flags.append("--last")
    if options.nth is not None:
        _opt(flags, "--nth", str(_bounded_int(options.nth, "nth", 0, 10_000)))
    if options.limit is not None:
        _opt(flags, "--limit", str(_bounded_int(options.limit, "limit", 0, 10_000)))


def _skills(flags: list[str], positionals: list[str], options: DesktopOptions) -> None:
    action = options.subcommand or "list"
    if action not in _SKILL_ACTIONS:
        raise ValueError("skills subcommand must be list, get, or path")
    positionals.append(action)
    if action == "get":
        if not options.skill:
            raise ValueError(
                "skills get requires options.skill, such as desktop or platform"
            )
        positionals.append(_line(options.skill, "skill"))
        if options.reference:
            positionals.append(_line(options.reference, "reference"))
        _mark(flags, "--full", options.full)
    elif options.skill or options.reference or options.full:
        raise ValueError("skill, reference, and full are only used by skills get")


def _session(flags: list[str], positionals: list[str], options: DesktopOptions) -> None:
    action = options.subcommand
    if action not in _SESSION_ACTIONS:
        raise ValueError("session subcommand must be start, end, list, or gc")
    positionals.append(action)
    if action == "start":
        if options.label:
            label = _text(options.label, "label")
            if not label or len(label.encode("utf-8")) > 128:
                raise ValueError("session label must be 1 to 128 bytes")
            _opt(flags, "--name", label)
        if options.screenshots and options.no_trace:
            raise ValueError(
                "session screenshots requires tracing; do not set no_trace"
            )
        if options.multi_agent and not options.cursor:
            raise ValueError("session multi_agent requires cursor")
        _mark(flags, "--no-trace", options.no_trace)
        _mark(flags, "--screenshots", options.screenshots)
        _mark(flags, "--cursor", options.cursor)
        _mark(flags, "--multi-agent", options.multi_agent)
    elif (
        options.label
        or options.no_trace
        or options.screenshots
        or options.cursor
        or options.multi_agent
    ):
        raise ValueError("session start flags are only used by subcommand start")
    if action == "end" and options.session_id:
        resolved = _optional_session(options.session_id)
        if not resolved:
            raise ValueError("session_id must be an agent-desktop session id")
        positionals.append(resolved)
    elif options.session_id:
        raise ValueError("session_id is only used by session end")
    if action == "gc":
        if options.older_than is not None:
            _opt(
                flags,
                "--older-than",
                str(_bounded_int(options.older_than, "older_than", 0, 86_400_000)),
            )
        _mark(flags, "--ended", options.ended)
    elif options.older_than is not None or options.ended:
        raise ValueError("older_than and ended are only used by session gc")


def _wait(flags: list[str], positionals: list[str], options: DesktopOptions) -> None:
    selected: list[str] = []
    if options.ms is not None:
        selected.append("ms")
    if options.element:
        selected.append("element")
    if options.menu:
        selected.append("menu")
    if options.menu_closed:
        selected.append("menu_closed")
    if options.notification:
        selected.append("notification")
    if options.event:
        selected.append("event")
    if options.window_title and not options.event:
        selected.append("window")
    if options.text and not options.notification:
        selected.append("text")
    if len(selected) != 1:
        raise ValueError(
            "wait needs exactly one mode: ms, element, window_title, text, "
            "menu, menu_closed, notification, or event"
        )
    mode = selected[0]
    if mode == "ms":
        if options.ms is None:
            raise ValueError("wait ms is required for a timed wait")
        positionals.append(str(_bounded_int(options.ms, "ms", 0, 86_400_000)))
        return
    if mode == "element":
        _opt(flags, "--element", _ref(options.element or "", "element"))
        if options.predicate:
            _opt(flags, "--predicate", options.predicate)
        if options.predicate == "value":
            if options.value is None:
                raise ValueError("wait predicate value requires options.value")
            _opt(flags, "--value", _text(options.value, "value"))
        elif options.value is not None:
            raise ValueError("wait value is only used with predicate value")
        if options.action_name:
            if options.action_name not in {"click", "type", "set-value", "clear"}:
                raise ValueError(
                    "wait action_name must be click, type, set-value, or clear"
                )
            _opt(flags, "--action", options.action_name)
    elif mode == "window":
        _opt(flags, "--window", _line(options.window_title or "", "window_title"))
        if options.app:
            _opt(flags, "--app", _line(options.app, "app"))
    elif mode == "text":
        _opt(flags, "--text", _line(options.text or "", "text"))
        if options.text_count is not None:
            _opt(
                flags,
                "--count",
                str(_bounded_int(options.text_count, "text_count", 0, 10_000)),
            )
        if options.app:
            _opt(flags, "--app", _line(options.app, "app"))
    elif mode == "menu":
        flags.append("--menu")
        if options.app:
            _opt(flags, "--app", _line(options.app, "app"))
    elif mode == "menu_closed":
        flags.append("--menu-closed")
        if options.app:
            _opt(flags, "--app", _line(options.app, "app"))
    elif mode == "notification":
        flags.append("--notification")
        if options.text:
            _opt(flags, "--text", _line(options.text, "text"))
        if options.app:
            _opt(flags, "--app", _line(options.app, "app"))
    else:
        _opt(flags, "--event", options.event or "")
        if options.app:
            _opt(flags, "--app", _line(options.app, "app"))
        if options.window_title:
            _opt(flags, "--window", _line(options.window_title, "window_title"))
        if options.window_id:
            _opt(flags, "--window-id", _token(options.window_id, "window_id"))
    _timeout_flag(flags, options, flag="--timeout")


def _hover(flags: list[str], positionals: list[str], options: DesktopOptions) -> None:
    if bool(options.ref) == bool(options.xy):
        raise ValueError("hover requires options.ref or options.xy, not both")
    if options.ref:
        positionals.append(_ref(options.ref))
    else:
        _opt(flags, "--xy", _xy(options.xy or ""))
    _timeout_flag(flags, options)


def _drag(flags: list[str], options: DesktopOptions) -> None:
    if bool(options.from_ref) == bool(options.from_xy):
        raise ValueError("drag requires one of from_ref or from_xy")
    if bool(options.to_ref) == bool(options.to_xy):
        raise ValueError("drag requires one of to_ref or to_xy")
    if options.from_ref:
        _opt(flags, "--from", _ref(options.from_ref, "from_ref"))
    else:
        _opt(flags, "--from-xy", _xy(options.from_xy or ""))
    if options.to_ref:
        _opt(flags, "--to", _ref(options.to_ref, "to_ref"))
    else:
        _opt(flags, "--to-xy", _xy(options.to_xy or ""))
    if options.duration_ms is not None:
        _opt(
            flags,
            "--duration",
            str(_bounded_int(options.duration_ms, "duration_ms", 0, 60_000)),
        )
    if options.drop_delay_ms is not None:
        _opt(
            flags,
            "--drop-delay",
            str(_bounded_int(options.drop_delay_ms, "drop_delay_ms", 0, 10_000)),
        )
    if options.wait_for_scope:
        _opt(flags, "--wait-for-scope", options.wait_for_scope)
    _timeout_flag(flags, options)


def _clipboard_set(
    flags: list[str], positionals: list[str], options: DesktopOptions
) -> None:
    chosen = sum(
        bool(item)
        for item in (options.file_urls, options.image, options.text is not None)
    )
    if chosen != 1:
        raise ValueError("clipboard-set takes one of text, image, or file_urls")
    if options.file_urls:
        for path in options.file_urls:
            _opt(flags, "--file-url", _path(path, "file_urls"))
        return
    if options.image:
        _opt(flags, "--image", _path(options.image, "image"))
        return
    if options.text is None:
        raise ValueError("clipboard-set requires options.text, image, or file_urls")
    positionals.append(_text(options.text, "text"))


def _batch(flags: list[str], positionals: list[str], options: DesktopOptions) -> None:
    entries = options.entries
    if not entries:
        raise ValueError("batch requires options.entries")
    if len(entries) > 64:
        raise ValueError("batch accepts at most 64 entries")
    cleaned: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"batch entry {index} must be an object")
        extra = set(entry) - {"command", "args", "session"}
        if extra:
            names = ", ".join(sorted(str(name) for name in extra))
            raise ValueError(f"batch entry {index} has unknown keys: {names}")
        name = entry.get("command")
        if not isinstance(name, str) or name not in DESKTOP_COMMANDS or name == "batch":
            raise ValueError(f"batch entry {index} command {name!r} is not allowed")
        if name in HELD_INPUT:
            raise ValueError(f"batch entry {index} cannot run {name}")
        args = entry.get("args", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ValueError(f"batch entry {index} args must be an object")
        item: dict[str, Any] = {"command": name, "args": args}
        if "session" in entry:
            if not isinstance(entry["session"], str):
                raise ValueError(f"batch entry {index} session must be a string")
            session_id = _optional_session(entry["session"])
            if not session_id:
                raise ValueError(f"batch entry {index} session must be a session id")
            item["session"] = session_id
        cleaned.append(item)
    payload = json.dumps(cleaned, separators=(",", ":"))
    if len(payload.encode("utf-8")) > 1_000_000:
        raise ValueError("batch entries exceed 1 MiB")
    positionals.append(payload)
    _mark(flags, "--stop-on-error", options.stop_on_error)
    _timeout_flag(flags, options)


def _notification_index(positionals: list[str], options: DesktopOptions) -> None:
    if options.index is None:
        raise ValueError("a notification index from list-notifications is required")
    positionals.append(str(_bounded_int(options.index, "index", 1, 10_000)))


def _expected(flags: list[str], options: DesktopOptions) -> None:
    if not options.expected_app and not options.expected_title:
        raise ValueError(
            "dismiss and notification-action require options.expected_app or "
            "expected_title from the same list-notifications result"
        )
    if options.expected_app:
        _opt(flags, "--expected-app", _line(options.expected_app, "expected_app"))
    if options.expected_title:
        _opt(flags, "--expected-title", _line(options.expected_title, "expected_title"))


def _wait_flags(flags: list[str], options: DesktopOptions, command: str) -> None:
    if not (
        options.wait_for or options.wait_for_gone or options.wait_timeout_ms is not None
    ):
        return
    if options.wait_for and options.wait_for_gone:
        raise ValueError("pass only one of wait_for and wait_for_gone")
    if command == "snapshot" and options.root:
        raise ValueError("snapshot root cannot be combined with wait_for")
    if options.wait_for:
        _opt(flags, "--wait-for", _line(options.wait_for, "wait_for"))
    if options.wait_for_gone:
        _opt(flags, "--wait-for-gone", _line(options.wait_for_gone, "wait_for_gone"))
    if options.wait_timeout_ms is not None:
        _opt(
            flags,
            "--wait-timeout",
            str(
                _bounded_int(options.wait_timeout_ms, "wait_timeout_ms", 0, 86_400_000)
            ),
        )


def _app_window(flags: list[str], options: DesktopOptions) -> None:
    if options.app:
        _opt(flags, "--app", _line(options.app, "app"))
    if options.window_id:
        _opt(flags, "--window-id", _token(options.window_id, "window_id"))


def _timeout_flag(
    flags: list[str], options: DesktopOptions, *, flag: str = "--timeout-ms"
) -> None:
    if options.timeout_ms is None:
        return
    _opt(
        flags,
        flag,
        str(_bounded_int(options.timeout_ms, "timeout_ms", 0, 86_400_000)),
    )


def _modifiers(flags: list[str], options: DesktopOptions) -> None:
    for name in options.modifiers or []:
        if name not in _MODIFIERS:
            choices = ", ".join(sorted(_MODIFIERS))
            raise ValueError(f"modifier must be one of: {choices}")
        _opt(flags, "--modifiers", name)


def _require_ref(options: DesktopOptions) -> str:
    if not options.ref:
        raise ValueError(
            "this command requires options.ref, a qualified ref such as @s8f3k2p9:e8"
        )
    return _ref(options.ref)


def _ref(value: str, label: str = "ref") -> str:
    text = _line(value, label)
    if not _REF.fullmatch(text):
        raise ValueError(
            f"{label} must be a snapshot-qualified ref such as @s8f3k2p9:e8. "
            "A bare @eN ref is rejected."
        )
    return text


def _state(value: str) -> str:
    text = _line(value, "states")
    token, separator, raw = text.partition("=")
    if token not in _STATE_TOKENS or (separator and raw not in {"true", "false"}):
        raise ValueError(
            "states entries look like checked or checked=false. "
            f"Unknown token {token!r}."
        )
    return text


def _surface_token(value: str) -> str:
    text = _line(value, "surface")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", text):
        raise ValueError(
            "surface must be a lowercase surface kind such as window or menu"
        )
    return text


def _optional_session(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if not _SESSION.fullmatch(text):
        raise ValueError(
            "session must be an agent-desktop session id (letters, digits, ., _, :, -)"
        )
    return text


def _token(value: str, label: str) -> str:
    text = _line(value, label)
    if not _TOKEN.fullmatch(text):
        raise ValueError(f"{label} contains characters this command will not accept")
    return text


def _xy(value: str) -> str:
    text = _line(value, "xy")
    if not _XY.fullmatch(text):
        raise ValueError("coordinates must look like 640,400")
    return text


def _path(value: str, label: str) -> str:
    text = _line(value, label)
    if text.startswith("-"):
        raise ValueError(f"{label} must not start with '-'")
    return text


def _line(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if (
        re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value)
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{label} must be a single line")
    if len(value) > 10_000:
        raise ValueError(f"{label} is too long")
    if value.startswith("-") and label in {"app", "combo"}:
        raise ValueError(f"{label} must not start with '-'")
    return value


def _text(value: str, label: str) -> str:
    text = _line(value, label)
    if len(text.encode("utf-8")) > 10_000:
        raise ValueError(f"{label} must be at most 10000 bytes")
    return text


def _bounded_int(value: int, label: str, low: int, high: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not low <= value <= high
    ):
        raise ValueError(f"{label} must be an integer from {low} to {high}")
    return value


def _number(value: float, label: str) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{label} must be a finite number")
    return str(value)


def _positive_number(value: float, label: str) -> str:
    rendered = _number(value, label)
    if float(rendered) <= 0:
        raise ValueError(f"{label} must be greater than 0")
    return rendered


def _opt(argv: list[str], flag: str, value: str) -> None:
    if value.startswith("-"):
        argv.append(f"{flag}={value}")
    else:
        argv.extend([flag, value])


def _mark(argv: list[str], flag: str, enabled: bool) -> None:
    if enabled:
        argv.append(flag)
