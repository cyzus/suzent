import asyncio
import sys
from collections.abc import Coroutine
from typing import Annotated, Any, Literal, TypeVar
from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    CDPSession,
    ElementHandle,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
from starlette.websockets import WebSocket
from pydantic import Field, ValidationError
from suzent.tools.browser_config import (
    BrowserCommand,
    BrowserSettings,
    normalize_browser_url,
)
from suzent.tools.browser_connection import discover_browser_endpoint
from suzent.tools.browser_snapshot import (
    SNAPSHOT_SCRIPT,
    ELEMENT_STATE_SCRIPT,
    CONTROLS_READY_SCRIPT,
    format_snapshot_element,
)
from suzent.tools.base import Tool, ToolGroup, ToolErrorCode, ToolResult
from suzent.logger import get_logger
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps

logger = get_logger(__name__)
T = TypeVar("T")


class BrowserSessionManager:
    _instance = None

    def __init__(self, settings: BrowserSettings | None = None) -> None:
        self._reload_settings = settings is None
        self.settings = settings or BrowserSettings.load()
        self._action_lock = asyncio.Lock()
        self._snapshot_generation = 0
        self._selector_map: dict[str, tuple[ElementHandle, dict[str, Any]]] = {}
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._client: CDPSession | None = None
        self._websockets: list[WebSocket] = []
        self._streaming = False
        self._attached = False
        self._tabs: dict[str, Page] = {}
        self._next_tab_id = 0
        self._init_lock: asyncio.Lock | None = None

    @classmethod
    def get_instance(cls) -> "BrowserSessionManager":
        if cls._instance is None:
            cls._instance = BrowserSessionManager()
        return cls._instance

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the main application event loop for thread safety."""
        self._main_loop = loop
        # Initialize lock on the main loop
        self._init_lock = asyncio.Lock()

    async def _run_on_main_loop(self, coro: Coroutine[Any, Any, T]) -> T:
        """Execute a coroutine on the main loop, handling cross-thread awaiting."""
        # If no main loop set (e.g. testing), try to use current or assume safety
        if not hasattr(self, "_main_loop") or self._main_loop is None:
            # Only warn once to avoid log spam
            if not getattr(self, "_warned_loop", False):
                logger.warning(
                    "No main loop set for BrowserSessionManager. Assuming current loop."
                )
                self._warned_loop = True
            return await coro

        # If we are already on the main loop, just await
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop is self._main_loop:
                logger.debug("Already on main loop, awaiting coroutine directly.")
                return await coro
        except RuntimeError:
            logger.debug("No running loop in current thread.")
            pass

        # Otherwise, we are in a worker thread/loop -> dispatch to main
        logger.debug("Dispatching coroutine to main loop via threadsafe future.")
        future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)

        try:
            # Add a timeout to avoid infinite hangs in the synchronization layer
            return await asyncio.wait_for(asyncio.wrap_future(future), timeout=60.0)
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for main loop coroutine to complete.")
            raise RuntimeError("Browser action timed out during loop synchronization.")

    async def ensure_session(self, headless: bool | None = None) -> bool:
        """Apply saved settings between actions; return whether a session was replaced."""

        async def _launch() -> bool:
            if self._init_lock is None:
                self._init_lock = asyncio.Lock()
            async with self._init_lock, self._action_lock:
                desired = (
                    await asyncio.to_thread(BrowserSettings.load)
                    if self._reload_settings
                    else self.settings
                )
                changed = desired != self.settings
                replaced = self._page is not None
                if (
                    not changed
                    and self._page
                    and not self._page.is_closed()
                    and self._browser
                    and self._browser.is_connected()
                ):
                    return False
                await self.close_session()
                self.settings = desired
                try:
                    self._playwright = await async_playwright().start()
                    try:
                        await self._launch_context(headless)
                    except Exception as exc:
                        if (
                            self.settings.channel != "chromium"
                            or "executable doesn't exist" not in str(exc).lower()
                        ):
                            raise
                        logger.info("Installing missing Chromium browser")
                        process = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "playwright",
                            "install",
                            "chromium",
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        try:
                            code = await asyncio.wait_for(process.wait(), timeout=120)
                        except BaseException:
                            if process.returncode is None:
                                process.kill()
                            await process.wait()
                            raise
                        if code != 0:
                            raise RuntimeError(
                                "Chromium installation failed. Run uv run playwright install chromium."
                            ) from None
                        await self._launch_context(headless)
                    self._context.set_default_timeout(5000)
                    self._context.set_default_navigation_timeout(15000)
                    self._page = (
                        await self._context.new_page()
                        if self._attached
                        else next(iter(self._context.pages), None)
                        or await self._context.new_page()
                    )
                    self._page.on("framenavigated", self._on_navigation)
                    self._client = await self._context.new_cdp_session(self._page)
                    self._client.on("Page.screencastFrame", self._on_screencast_frame)
                    if self._websockets:
                        await self.start_streaming()
                    logger.info("Browser session started")
                    return replaced
                except BaseException:
                    await self.close_session()
                    raise

        return await self._run_on_main_loop(_launch())

    async def _launch_context(self, headless: bool | None) -> None:
        if self.settings.connection_mode == "existing":
            endpoint = await asyncio.to_thread(
                discover_browser_endpoint, self.settings.channel
            )
            self._attached = True
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    endpoint, timeout=30000
                )
            except PlaywrightError:
                raise ValueError(
                    "Could not attach to the selected browser. Keep it running, enable "
                    "remote debugging in its inspect page, and approve the browser's "
                    "connection prompt before retrying."
                ) from None
            self._context = self._browser.contexts[0]
            return
        options = {
            "headless": self.settings.headless if headless is None else headless,
            "channel": None
            if self.settings.channel == "chromium"
            else self.settings.channel,
            "timeout": 30000,
        }
        if self.settings.persistent:
            profile = self.settings.profile_dir.expanduser().resolve()
            profile.mkdir(parents=True, exist_ok=True)
            self._context = await self._playwright.chromium.launch_persistent_context(
                str(profile),
                viewport={"width": 1280, "height": 800},
                **options,
            )
            self._browser = self._context.browser
        else:
            self._browser = await self._playwright.chromium.launch(**options)
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800}
            )

    async def tabs(self) -> ToolResult:
        async def _list() -> ToolResult:
            async with self._action_lock:
                pages = self._context.pages
                self._tabs = {
                    key: page for key, page in self._tabs.items() if page in pages
                }
                for page in pages:
                    if page not in self._tabs.values():
                        self._next_tab_id += 1
                        self._tabs[f"tab-{self._next_tab_id}"] = page
                items = [
                    {"id": key, "url": page.url, "selected": page == self._page}
                    for key, page in self._tabs.items()
                ]
                return ToolResult.success_result(
                    "\n".join(
                        f"{item['id']} {'*' if item['selected'] else ''} {item['url']}"
                        for item in items
                    ),
                    metadata={"tabs": items},
                )

        return await self._run_on_main_loop(_list())

    async def select_tab(self, tab_id: str) -> ToolResult:
        async def _select() -> ToolResult:
            async with self._action_lock:
                page = self._tabs.get(tab_id)
                if page is None or page.is_closed():
                    return ToolResult.error_result(
                        ToolErrorCode.INVALID_ARGUMENT,
                        "Tab expired or unknown. Call tabs again.",
                    )
                await self.stop_streaming()
                await self._dispose_refs()
                self._snapshot_generation += 1
                if self._client:
                    await self._client.detach()
                if self._page:
                    self._page.remove_listener("framenavigated", self._on_navigation)
                self._page = page
                page.on("framenavigated", self._on_navigation)
                self._client = await self._context.new_cdp_session(page)
                self._client.on("Page.screencastFrame", self._on_screencast_frame)
                if self._websockets:
                    await self.start_streaming()
                return ToolResult.success_result(
                    "Tab selected. Call snapshot before interacting."
                )

        return await self._run_on_main_loop(_select())

    def _on_navigation(self, frame: Any) -> None:
        if self._page and frame == self._page.main_frame:
            self._snapshot_generation += 1

    # --- Wrapper methods for Thread Safety ---

    async def goto(self, url: str) -> None:
        url = normalize_browser_url(url)

        async def _fn() -> None:
            async with self._action_lock:
                self._snapshot_generation += 1
                await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)

        await self._run_on_main_loop(_fn())

    async def click(self, x: int, y: int) -> None:
        async def _fn() -> None:
            async with self._action_lock:
                self._snapshot_generation += 1
                await self._page.mouse.click(x, y)

        await self._run_on_main_loop(_fn())

    async def scroll(self, dx: int, dy: int) -> None:
        async def _fn() -> None:
            async with self._action_lock:
                await self._page.mouse.wheel(dx, dy)

        await self._run_on_main_loop(_fn())

    async def back(self) -> None:
        async def _fn() -> None:
            async with self._action_lock:
                self._snapshot_generation += 1
                await self._page.go_back(wait_until="domcontentloaded")

        await self._run_on_main_loop(_fn())

    async def forward(self) -> None:
        async def _fn() -> None:
            async with self._action_lock:
                self._snapshot_generation += 1
                await self._page.go_forward(wait_until="domcontentloaded")

        await self._run_on_main_loop(_fn())

    async def reload(self) -> None:
        async def _fn() -> None:
            async with self._action_lock:
                self._snapshot_generation += 1
                await self._page.reload(wait_until="domcontentloaded")

        await self._run_on_main_loop(_fn())

    async def _dispose_refs(self) -> None:
        refs, self._selector_map = self._selector_map, {}
        for element, _ in refs.values():
            try:
                await element.dispose()
            except Exception:
                pass

    async def get_snapshot(
        self, interactive_only: bool = False, offset: int = 0, limit: int = 80
    ) -> ToolResult:
        async def _snap() -> ToolResult:
            async with self._action_lock:
                await self._dispose_refs()
                self._snapshot_generation += 1
                generation = self._snapshot_generation
                snapshot = None
                try:
                    await self._page.wait_for_load_state(
                        "domcontentloaded", timeout=5000
                    )
                    # Hydration can follow DOMContentLoaded; empty documents remain valid observations.
                    try:
                        ready = await self._page.wait_for_function(
                            CONTROLS_READY_SCRIPT, timeout=750
                        )
                        await ready.dispose()
                    except PlaywrightTimeoutError:
                        pass
                    snapshot = await self._page.evaluate_handle(
                        SNAPSHOT_SCRIPT,
                        {
                            "offset": offset,
                            "limit": limit,
                            "interactiveOnly": interactive_only,
                        },
                    )
                    data_handle = await snapshot.get_property("data")
                    try:
                        data = await data_handle.json_value()
                    finally:
                        await data_handle.dispose()
                    nodes = await snapshot.get_property("nodes")
                    try:
                        properties = await nodes.get_properties()
                    finally:
                        await nodes.dispose()
                    for index, item in enumerate(data["items"]):
                        element = properties[str(index)].as_element()
                        ref = f"@g{generation}e{offset + index}"
                        self._selector_map[ref] = (element, item)
                    if generation != self._snapshot_generation:
                        await self._dispose_refs()
                        return ToolResult.error_result(
                            ToolErrorCode.EXECUTION_FAILED,
                            "Page navigated during observation. Call snapshot again.",
                        )
                    metadata = {
                        key: value
                        for key, value in data.items()
                        if key not in {"items", "text"}
                    }
                    metadata.update(
                        {
                            "snapshot_id": generation,
                            "offset": offset,
                            "element_count": len(data["items"]),
                            "interactive_only": interactive_only,
                        }
                    )
                    next_offset = offset + len(data["items"])
                    metadata["truncated"] = next_offset < data["total"]
                    lines = [
                        f"[Page: {data['title'][:200]} | URL: {data['url'][:1000]} | State: {data['ready_state']} | Snapshot: {generation}]"
                    ]
                    if data["text"]:
                        lines.append(data["text"])
                    if data["text_truncated"]:
                        lines.append("[Page text truncated to 4000 characters.]")
                    for ref, (_, item) in self._selector_map.items():
                        lines.append(format_snapshot_element(ref, item))
                    if not data["items"]:
                        lines.append(
                            "No interactive elements in this range. The page may be loading or contain no controls."
                        )
                    if metadata["truncated"]:
                        metadata["next_offset"] = next_offset
                        lines.append(
                            f'More elements: snapshot arguments=["{next_offset}", "{limit}"]. New snapshots expire previous refs.'
                        )
                    if data["frame_count"]:
                        lines.append(
                            "[Embedded frames are not included in this snapshot.]"
                        )
                    return ToolResult.success_result(
                        "\n".join(lines), metadata=metadata
                    )
                except PlaywrightTimeoutError:
                    await self._dispose_refs()
                    return ToolResult.error_result(
                        ToolErrorCode.TIMEOUT,
                        "Page is still loading. Call snapshot again.",
                    )
                except Exception:
                    await self._dispose_refs()
                    return ToolResult.error_result(
                        ToolErrorCode.EXECUTION_FAILED,
                        "Snapshot failed; the page may have changed. Call snapshot again.",
                    )
                finally:
                    if snapshot is not None:
                        try:
                            await snapshot.dispose()
                        except Exception:
                            pass

        return await self._run_on_main_loop(_snap())

    async def interact(
        self, action: str, ref: str, value: str | None = None
    ) -> ToolResult:
        async def _act() -> ToolResult:
            async with self._action_lock:
                target = self._selector_map.get(ref)
                if target is None or not ref.startswith(
                    f"@g{self._snapshot_generation}e"
                ):
                    return ToolResult.error_result(
                        ToolErrorCode.INVALID_ARGUMENT,
                        "Ref expired or unknown. Call snapshot again.",
                    )
                element, observed = target
                try:
                    current = await element.evaluate(ELEMENT_STATE_SCRIPT)
                    if not current["connected"] or any(
                        current[key] != observed[key]
                        for key in ("tag", "type", "label", "href", "name")
                    ):
                        return ToolResult.error_result(
                            ToolErrorCode.INVALID_ARGUMENT,
                            "Element changed. Call snapshot again.",
                        )
                    match action:
                        case "click":
                            await element.click(timeout=5000)
                        case "dblclick":
                            await element.dblclick(timeout=5000)
                        case "hover":
                            await element.hover(timeout=5000)
                        case "fill":
                            await element.fill(value or "", timeout=5000)
                        case "type":
                            await element.type(value or "", timeout=5000)
                        case "press":
                            await element.press(value, timeout=5000)
                        case _:
                            return ToolResult.error_result(
                                ToolErrorCode.INVALID_ARGUMENT, "Unknown interaction."
                            )
                    return ToolResult.success_result(
                        f"{action} completed on {ref}.",
                        metadata={"action": action, "ref": ref},
                    )
                except PlaywrightTimeoutError:
                    return ToolResult.error_result(
                        ToolErrorCode.TIMEOUT,
                        "Element was not actionable within 5 seconds. Call snapshot again.",
                    )
                except Exception:
                    return ToolResult.error_result(
                        ToolErrorCode.EXECUTION_FAILED,
                        "Interaction failed; the element may have changed. Call snapshot again.",
                    )

        return await self._run_on_main_loop(_act())

    async def _on_screencast_frame(self, params):
        """Handle incoming CDP screencast frames."""
        try:
            # Acknowledge the frame so CDP keeps sending them
            await self._client.send(
                "Page.screencastFrameAck", {"sessionId": params.get("sessionId")}
            )

            data = params.get("data")  # Base64 string
            metadata = params.get("metadata")

            if not data or not self._websockets:
                return

            # Broadcast to all connected websockets
            # We send raw bytes to avoid base64 overhead in WS if possible,
            # but for simplicity JSON wrapping might be safer initially.
            # Let's send a JSON message with the image.

            message = {
                "type": "frame",
                "data": data,
                "timestamp": metadata.get("timestamp"),
            }

            # Broadcast loop - use a copy to avoid modification during iteration
            disconnected = []
            for ws in list(self._websockets):
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)

            # Cleanup disconnected - safe removal (ws may already be removed by remove_client)
            for ws in disconnected:
                if ws in self._websockets:
                    self._websockets.remove(ws)

        except Exception as e:
            logger.error(f"Error handling screencast frame: {e}")

    async def start_streaming(self):
        # No-op if browser not initialized yet (lazy init)
        if self._streaming or not self._client:
            return
        logger.info("Starting CDP Screencast...")
        await self._client.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": 60,
                "maxWidth": 1280,
                "maxHeight": 800,
                "everyNthFrame": 1,  # Send every frame
            },
        )
        self._streaming = True

    async def stop_streaming(self):
        if not self._streaming or not self._client:
            return
        try:
            await self._client.send("Page.stopScreencast")
        except Exception as e:
            # Ignore if target is closed (browser/page already gone)
            logger.debug(f"Error stopping screencast (likely closed): {e}")
        self._streaming = False

    async def add_client(self, websocket: WebSocket):
        """Accept WebSocket client without launching browser (lazy init)."""
        await websocket.accept()
        self._websockets.append(websocket)
        # If browser already running, start streaming for this client
        if self._client and not self._streaming:
            await self.start_streaming()
        # Otherwise, browser will be launched lazily when needed

    async def remove_client(self, websocket: WebSocket):
        if websocket in self._websockets:
            self._websockets.remove(websocket)
        # If no clients left, maybe stop streaming to save resources?
        if not self._websockets:
            await self.stop_streaming()

    def _get_mouse_coords(self, message: dict) -> tuple[float | None, float | None]:
        """Extract and validate mouse coordinates from a message."""
        return message.get("x"), message.get("y")

    async def handle_client_message(self, message: dict[str, Any]) -> None:
        async def _handle() -> None:
            if message.get("type") == "navigate":
                await self._handle_client_message(message)
                return
            async with self._action_lock:
                self._snapshot_generation += 1
                await self._handle_client_message(message)

        await self._run_on_main_loop(_handle())

    async def _handle_client_message(self, message: dict[str, Any]) -> None:
        """Process interaction events from the frontend."""
        action = message.get("type")

        # Lazy init: launch browser on navigate command
        if action == "navigate":
            url = message.get("url")
            if url:
                await self.ensure_session()
                await self.start_streaming()
                await self.goto(normalize_browser_url(url))
            return

        # Other actions require browser to be already running
        if not self._page:
            return

        try:
            # Mouse actions with coordinate validation
            if action in ("click", "mousedown", "mouseup", "mousemove"):
                x, y = self._get_mouse_coords(message)
                if x is None or y is None:
                    return

                if action == "click":
                    await self._page.mouse.click(x, y)
                elif action == "mousedown":
                    await self._page.mouse.move(x, y)
                    await self._page.mouse.down()
                elif action == "mouseup":
                    await self._page.mouse.move(x, y)
                    await self._page.mouse.up()
                elif action == "mousemove":
                    await self._page.mouse.move(x, y)

            elif action == "type":
                text = message.get("text")
                if text:
                    await self._page.keyboard.type(text)

            elif action == "key":
                key = message.get("key")
                if key:
                    await self._page.keyboard.press(key)

            elif action == "scroll":
                dx, dy = message.get("dx", 0), message.get("dy", 0)
                await self._page.mouse.wheel(dx, dy)

        except Exception as e:
            logger.error(f"Error handling client browser interaction: {e}")

    async def close_session(self):
        """Clean up browser resources."""
        logger.info("Closing Browser Session...")
        await self.stop_streaming()
        self._snapshot_generation += 1
        await self._dispose_refs()

        if self._page:
            self._page.remove_listener("framenavigated", self._on_navigation)
        if self._client:
            try:
                await self._client.detach()
            except Exception:
                pass
        if self._context and not self._attached:
            try:
                await self._context.close()
            except Exception as e:
                logger.debug(f"Ignored error closing context: {e}")
            self._context = None

        if self._browser and not self._attached:
            try:
                await self._browser.close()
            except Exception as e:
                # Common race condition on Ctrl+C: driver dies before we close
                logger.debug(
                    f"Ignored error closing browser (likely already closed): {e}"
                )
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug(f"Ignored error stopping playwright: {e}")
            self._playwright = None

        self._context = None
        self._browser = None
        self._attached = False
        self._tabs.clear()
        self._page = None
        self._client = None
        logger.info("Browser Session Closed.")


class BrowsingTool(Tool):
    name = "BrowsingTool"
    tool_name = "browser_action"
    group = ToolGroup.WEB

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session_mgr = BrowserSessionManager.get_instance()

    async def _execute(
        self, command: str, arguments: list[str] | None = None
    ) -> ToolResult:
        try:
            request = BrowserCommand.model_validate(
                {
                    "command": command,
                    "arguments": arguments if arguments is not None else [],
                }
            )
        except ValidationError as exc:
            details = "; ".join(
                error["msg"] for error in exc.errors(include_input=False)
            )
            return ToolResult.error_result(ToolErrorCode.INVALID_ARGUMENT, details)
        args = request.arguments
        try:
            if (
                isinstance(self.session_mgr, BrowserSessionManager)
                and self.session_mgr._reload_settings
            ):
                from suzent.browser_extension.session import session as extension

                async def extension_action() -> ToolResult | None:
                    settings = await asyncio.to_thread(BrowserSettings.load)
                    if settings.connection_mode == "extension":
                        async with self.session_mgr._action_lock:
                            if self.session_mgr._playwright:
                                await self.session_mgr.close_session()
                            return await extension.execute(
                                request, interactive_only=arguments == ["-i"]
                            )
                    if extension.selected:
                        await extension.close()
                    return None

                result = await self.session_mgr._run_on_main_loop(extension_action())
                if result is not None:
                    return result
            replaced = await self.session_mgr.ensure_session()
            if replaced and request.command not in {
                "open",
                "snapshot",
                "tabs",
                "select_tab",
            }:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "Browser connection changed or restarted. Open a page or call snapshot before interacting.",
                )
            match request.command:
                case "tabs":
                    return await self.session_mgr.tabs()
                case "select_tab":
                    return await self.session_mgr.select_tab(args[0])
                case "snapshot":
                    return await self.session_mgr.get_snapshot(
                        interactive_only=arguments == ["-i"],
                        offset=int(args[0]) if args else 0,
                        limit=int(args[1]) if len(args) > 1 else 80,
                    )
                case "click" | "dblclick" | "hover" | "fill" | "type" | "press":
                    return await self.session_mgr.interact(
                        command, args[0], args[1] if len(args) > 1 else None
                    )
                case "open":
                    await self.session_mgr.goto(args[0])
                case "back":
                    await self.session_mgr.back()
                case "forward":
                    await self.session_mgr.forward()
                case "reload" | "refresh":
                    await self.session_mgr.reload()
                case "click_coords":
                    await self.session_mgr.click(int(args[0]), int(args[1]))
                case "scroll":
                    await self.session_mgr.scroll(int(args[0]), int(args[1]))
            return ToolResult.success_result(
                f"{command} completed. Call snapshot to observe the page.",
                metadata={"command": command},
            )
        except ValueError as exc:
            return ToolResult.error_result(ToolErrorCode.INVALID_ARGUMENT, str(exc))
        except PlaywrightTimeoutError:
            return ToolResult.error_result(
                ToolErrorCode.TIMEOUT,
                "Browser action timed out. Call snapshot to inspect the current page before retrying.",
            )
        except Exception:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                "Browser action failed. Check browser installation/profile configuration, or call snapshot if a page is open.",
            )

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        command: Annotated[
            Literal[
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
            ],
            Field(description="Browser command to execute."),
        ],
        arguments: Annotated[
            list[str] | None,
            Field(
                default=None,
                description="tabs: [] lists stable tab IDs; select_tab: [tab-id] switches tabs; open: [url] or []; snapshot: [] or [offset, limit<=100] or [-i]; click/dblclick/hover: [ref]; fill/type/press: [ref, value]; click_coords: [x, y]; scroll: [dx, dy] or []; back/forward/reload/refresh: []. Use exact @gNeN refs from the latest snapshot; selectors are not accepted.",
            ),
        ] = None,
    ) -> ToolResult:
        """Control a browser session to navigate and interact with web pages.

        Optimal workflow: open <url>, then snapshot to get element refs, then click/fill using refs.

        Args:
            command: The command to execute (open, snapshot, click, fill, scroll, back, forward, refresh, click_coords).
            arguments: Command-specific string arguments. Refs expire after navigation or another snapshot.
        """
        return await self._execute(command, arguments)
