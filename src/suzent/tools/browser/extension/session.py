"""Browser actions over the extension's tab-scoped debugger connection."""

import asyncio
import json
from typing import Any

from starlette.websockets import WebSocket

from suzent.tools.base import ToolResult
from suzent.tools.browser.preview import PreviewFrames
from suzent.tools.browser.config import BrowserCommand
from suzent.tools.browser.snapshot import (
    SNAPSHOT_SCRIPT,
    ELEMENT_STATE_SCRIPT,
    CONTROLS_READY_SCRIPT,
    format_snapshot_element,
)
from suzent.tools.browser.extension.bridge import bridge


class ExtensionSession:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.clients: list[WebSocket] = []
        self.generation = 0
        self.connection_generation = -1
        self.selected: str | None = None
        self.refs: dict[str, tuple[int, dict[str, Any]]] = {}
        self.world: int | None = None
        self.streaming = False
        self.frames = PreviewFrames(self.clients)
        bridge.on_event = self.on_event
        bridge.on_disconnect = self.reset

    def invalidate(self) -> None:
        self.generation += 1
        self.refs.clear()

    async def cdp(self, method: str, **params: Any) -> Any:
        return await bridge.request("cdp", method=method, params=params)

    async def evaluate(self, expression: str) -> Any:
        result = await self.cdp(
            "Runtime.evaluate",
            expression=expression,
            contextId=self.world,
            returnByValue=True,
        )
        if result.get("exceptionDetails"):
            raise ValueError("Page changed during the action. Take a fresh snapshot.")
        return result["result"].get("value")

    async def on_event(self, method: str, params: dict[str, Any]) -> None:
        if method == "Page.frameNavigated" and not params.get("frame", {}).get(
            "parentId"
        ):
            self.invalidate()
            self.world = None
        elif method == "detached":
            await self.reset()
        elif method == "Page.screencastFrame":
            metadata = params.get("metadata", {})
            self.frames.offer(
                {
                    "type": "frame",
                    "data": params["data"],
                    "width": metadata.get("deviceWidth"),
                    "height": metadata.get("deviceHeight"),
                }
            )

    async def start_streaming(self) -> None:
        if self.clients and self.selected and not self.streaming:
            # Full-size frames keep preview input coordinates in CSS pixels.
            await self.cdp(
                "Page.startScreencast", format="jpeg", quality=60, everyNthFrame=1
            )
            self.streaming = True

    async def remove_client(self, client: WebSocket) -> None:
        if client in self.clients:
            self.clients.remove(client)
        async with self.lock:
            if not self.clients and self.streaming:
                try:
                    await self.cdp("Page.stopScreencast")
                except (ValueError, RuntimeError):
                    pass
                self.streaming = False
            if not self.clients:
                await self.frames.clear()

    async def close(self) -> None:
        async with self.lock:
            if bridge.socket and self.selected:
                await bridge.request("detach")
            await self.reset()

    async def reset(self) -> None:
        self.selected = None
        self.world = None
        self.streaming = False
        self.invalidate()
        await self.frames.clear()
        self.frames.offer({"type": "reset"})

    async def snapshot(self, args: list[str], interactive_only: bool) -> ToolResult:
        self.invalidate()
        generation = self.generation
        tree = await self.cdp("Page.getFrameTree")
        world = await self.cdp(
            "Page.createIsolatedWorld",
            frameId=tree["frameTree"]["frame"]["id"],
            worldName="suzent-browser",
        )
        self.world = world["executionContextId"]
        deadline = asyncio.get_running_loop().time() + 0.75
        while not await self.evaluate(f"({CONTROLS_READY_SCRIPT})()"):
            if asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(0.05)
        offset = int(args[0]) if args else 0
        limit = int(args[1]) if len(args) > 1 else 80
        options = json.dumps(
            {"offset": offset, "limit": limit, "interactiveOnly": interactive_only}
        )
        data = await self.evaluate(
            f"globalThis.__suzent = ({SNAPSHOT_SCRIPT})({options}); globalThis.__suzent.data"
        )
        if generation != self.generation:
            raise ValueError(
                "Page navigated during observation. Take a fresh snapshot."
            )
        lines = [
            f"[Page: {data['title'][:200]} | URL: {data['url'][:1000]} | State: {data['ready_state']} | Snapshot: {generation}]"
        ]
        if data["text"]:
            lines.append(data["text"])
        for index, item in enumerate(data["items"]):
            ref = f"@g{generation}e{offset + index}"
            self.refs[ref] = (index, item)
            lines.append(format_snapshot_element(ref, item))
        next_offset = offset + len(data["items"])
        if next_offset < data["total"]:
            lines.append(
                f'More elements: snapshot ["{next_offset}", "{limit}"]. Previous refs expire.'
            )
        if data["text_truncated"]:
            lines.append("[Page text truncated to 4000 characters.]")
        if data["frame_count"]:
            lines.append("[Embedded frames are not included.]")
        return ToolResult.success_result(
            "\n".join(lines),
            metadata={
                "snapshot_id": generation,
                "element_count": len(self.refs),
                "truncated": next_offset < data["total"],
                "next_offset": next_offset,
            },
        )

    async def interact(self, command: str, args: list[str]) -> None:
        target = self.refs.get(args[0])
        if target is None:
            raise ValueError("Ref expired or unknown. Take a fresh snapshot.")
        index, expected = target
        generation = self.generation
        expression = f"""(() => {{
          const el = globalThis.__suzent?.nodes[{index}];
          if (!el) throw new Error('expired');
          const current = ({ELEMENT_STATE_SCRIPT})(el);
          const expected = {json.dumps(expected)};
          if (!current.connected || ['tag','type','name','href','label'].some(k => current[k] !== expected[k])) throw new Error('changed');
          if (el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true') return null;
          el.scrollIntoView({{block:'center', inline:'center'}});
          const r = el.getBoundingClientRect();
          const x = r.x + r.width/2, y = r.y + r.height/2;
          const hit = document.elementFromPoint(x,y);
          if (!r.width || !r.height || !hit || !(hit === el || el.contains(hit))) return null;
          return {{x,y}};
        }})()"""
        deadline = asyncio.get_running_loop().time() + 5
        while True:
            point = await self.evaluate(expression)
            if point:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise ValueError(
                    "Element was not actionable within 5 seconds. Take a fresh snapshot."
                )
            await asyncio.sleep(0.1)
        if generation != self.generation:
            raise ValueError("Page changed. Take a fresh snapshot.")
        if command in {"click", "dblclick", "hover"}:
            await self.mouse("mouseMoved", **point)
            if command != "hover":
                for count in range(1, 3 if command == "dblclick" else 2):
                    await self.mouse(
                        "mousePressed", **point, button="left", clickCount=count
                    )
                    await self.mouse(
                        "mouseReleased", **point, button="left", clickCount=count
                    )
            return
        await self.evaluate(f"globalThis.__suzent.nodes[{index}].focus()")
        if command == "press":
            await self.key(args[1])
        else:
            if command == "fill":
                await self.evaluate(f"""(() => {{
                    const el = globalThis.__suzent.nodes[{index}];
                    if (el.matches('input, textarea')) el.select();
                    else if (el.isContentEditable) {{
                      const range = document.createRange(); range.selectNodeContents(el);
                      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
                    }} else throw new Error('not editable');
                }})()""")
            if args[1]:
                await self.cdp("Input.insertText", text=args[1])
            elif command == "fill":
                await self.key("Backspace")

    async def mouse(self, event: str, **params: Any) -> None:
        await self.cdp("Input.dispatchMouseEvent", type=event, **params)

    async def key(self, value: str) -> None:
        parts = value.split("+")
        modifiers = 0
        for part in parts[:-1]:
            if part not in {"Alt", "Control", "Meta", "Shift"}:
                raise ValueError("Unsupported key modifier.")
            modifiers |= {"Alt": 1, "Control": 2, "Meta": 4, "Shift": 8}.get(part, 0)
        key = parts[-1]
        codes = {
            "Enter": 13,
            "Tab": 9,
            "Backspace": 8,
            "Delete": 46,
            "Escape": 27,
            "ArrowLeft": 37,
            "ArrowUp": 38,
            "ArrowRight": 39,
            "ArrowDown": 40,
            "Home": 36,
            "End": 35,
            "PageUp": 33,
            "PageDown": 34,
        }
        code = codes.get(key, ord(key.upper()) if len(key) == 1 else 0)
        if not code:
            raise ValueError(
                "Unsupported key. Use a character, Enter, Tab, arrows, or a standard modifier chord."
            )
        params: dict[str, Any] = {
            "key": key,
            "windowsVirtualKeyCode": code,
            "modifiers": modifiers,
        }
        if key == "Enter":
            params["text"] = "\r"
        elif len(key) == 1 and not modifiers & 7:
            params["text"] = key
        await self.cdp("Input.dispatchKeyEvent", type="keyDown", **params)
        params.pop("text", None)
        await self.cdp("Input.dispatchKeyEvent", type="keyUp", **params)

    async def execute(
        self, request: BrowserCommand, interactive_only: bool = False
    ) -> ToolResult:
        async with self.lock:
            if self.connection_generation != bridge.generation:
                self.connection_generation = bridge.generation
                self.selected = None
                self.streaming = False
                self.world = None
                self.invalidate()
            command, args = request.command, request.arguments
            if command == "tabs":
                tabs = await bridge.request("tabs")
                return ToolResult.success_result(
                    "\n".join(
                        f"{tab['id']} {'*' if tab['selected'] else ''} {tab.get('title', '')} {tab['url']}"
                        for tab in tabs
                    ),
                    metadata={"tabs": tabs},
                )
            if command in {"open", "select_tab"}:
                result = (
                    await bridge.request("open", url=args[0])
                    if command == "open"
                    else await bridge.request("select", id=args[0])
                )
                self.selected = result["id"]
                self.world = None
                self.streaming = False
                self.invalidate()
                await self.start_streaming()
                return ToolResult.success_result(
                    "Page selected. Take a snapshot before interacting."
                )
            if not self.selected:
                raise ValueError(
                    "List tabs and select one, or open a page, before interacting."
                )
            if command == "snapshot":
                return await self.snapshot(args, interactive_only)
            if command in {"click", "dblclick", "hover", "fill", "type", "press"}:
                await self.interact(command, args)
            elif command == "click_coords":
                await self.mouse(
                    "mousePressed",
                    x=int(args[0]),
                    y=int(args[1]),
                    button="left",
                    clickCount=1,
                )
                await self.mouse(
                    "mouseReleased",
                    x=int(args[0]),
                    y=int(args[1]),
                    button="left",
                    clickCount=1,
                )
            elif command == "scroll":
                await self.mouse(
                    "mouseWheel", x=0, y=0, deltaX=int(args[0]), deltaY=int(args[1])
                )
            elif command in {"reload", "refresh"}:
                self.invalidate()
                await self.cdp("Page.reload")
            elif command in {"back", "forward"}:
                history = await self.cdp("Page.getNavigationHistory")
                index = history["currentIndex"] + (-1 if command == "back" else 1)
                if 0 <= index < len(history["entries"]):
                    self.invalidate()
                    await self.cdp(
                        "Page.navigateToHistoryEntry",
                        entryId=history["entries"][index]["id"],
                    )
            return ToolResult.success_result(
                f"{command} completed. Take a snapshot to observe the page."
            )

    async def handle_preview(self, message: dict[str, Any]) -> None:
        action = message.get("type")
        if action == "navigate":
            await self.execute(
                BrowserCommand(command="open", arguments=[message.get("url", "")])
            )
            return
        async with self.lock:
            if not self.selected:
                return
            if action == "type":
                await self.cdp("Input.insertText", text=message.get("text", ""))
            elif action == "key":
                await self.key(message.get("key", ""))
            elif action == "scroll":
                await self.mouse(
                    "mouseWheel",
                    x=0,
                    y=0,
                    deltaX=message.get("dx", 0),
                    deltaY=message.get("dy", 0),
                )
            elif action in {"mousedown", "mouseup", "mousemove"}:
                params = {"x": message["x"], "y": message["y"]}
                if action != "mousemove":
                    params.update(button="left", clickCount=1)
                await self.mouse(
                    {
                        "mousedown": "mousePressed",
                        "mouseup": "mouseReleased",
                        "mousemove": "mouseMoved",
                    }[action],
                    **params,
                )
            self.invalidate()


session = ExtensionSession()
