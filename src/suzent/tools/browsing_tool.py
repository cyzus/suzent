import asyncio
import base64
import json
from typing import Optional, Dict, List
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page, CDPSession
from starlette.websockets import WebSocket
from smolagents.tools import Tool
from suzent.logger import get_logger

logger = get_logger(__name__)

class BrowserSessionManager:
    _instance = None
    PORT = 9222
    
    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._client: Optional[CDPSession] = None
        self._websockets: List[WebSocket] = []
        self._streaming = False
        self._init_lock: Optional[asyncio.Lock] = None
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = BrowserSessionManager()
        return cls._instance
        
    def set_main_loop(self, loop):
        """Set the main application event loop for thread safety."""
        self._main_loop = loop
        # Initialize lock on the main loop
        self._init_lock = asyncio.Lock()
        
    async def _run_on_main_loop(self, coro):
        """Execute a coroutine on the main loop, handling cross-thread awaiting."""
        # If no main loop set (e.g. testing), try to use current or assume safety
        if not hasattr(self, "_main_loop") or self._main_loop is None:
            # Only warn once to avoid log spam
            if not getattr(self, "_warned_loop", False):
                logger.warning("No main loop set for BrowserSessionManager. Assuming current loop.")
                self._warned_loop = True
            return await coro

        # If we are already on the main loop, just await
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop is self._main_loop:
                return await coro
        except RuntimeError:
            pass # No running loop?

        # Otherwise, we are in a worker thread/loop -> dispatch to main
        future = asyncio.run_coroutine_threadsafe(coro, self._main_loop)
        return await asyncio.wrap_future(future)

    async def ensure_session(self, headless: bool = True):
        # We define the inner async function that does the actual work on the main loop
        async def _launch():
            if not self._init_lock:
                 logger.warning("No init lock available, potential race condition.")
                 # Create logical fallback lock if needed, but set_main_loop should be called.
                 self._init_lock = asyncio.Lock()

            async with self._init_lock:
                if self._page:
                    return

                logger.info("Starting Browser Session...")
                self._playwright = await async_playwright().start()
                
                args = [
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    f"--remote-debugging-port={self.PORT}"
                ]
                
                self._browser = await self._playwright.chromium.launch(
                    headless=headless, 
                    args=args
                )
                
                # Create context with video size tailored for sidebar
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 800}
                )
                self._page = await self._context.new_page()
                
                # Connect CDP for low-level control
                self._client = await self._context.new_cdp_session(self._page)
                
                # Setup Screencast
                self._client.on("Page.screencastFrame", self._on_screencast_frame)

        # Execute on main loop
        await self._run_on_main_loop(_launch())
        
    # --- Wrapper methods for Thread Safety ---
    
    async def goto(self, url: str):
        async def _fn():
             return await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return await self._run_on_main_loop(_fn())
        
    async def click(self, x: int, y: int):
        async def _fn():
            return await self._page.mouse.click(x, y)
        return await self._run_on_main_loop(_fn())
        
    async def scroll(self, dx: int, dy: int):
        async def _fn():
            return await self._page.mouse.wheel(dx, dy)
        return await self._run_on_main_loop(_fn())

    async def back(self):
        async def _fn():
             return await self._page.go_back(wait_until="domcontentloaded")
        return await self._run_on_main_loop(_fn())

    async def forward(self):
        async def _fn():
             return await self._page.go_forward(wait_until="domcontentloaded")
        return await self._run_on_main_loop(_fn())
        
    async def reload(self):
        async def _fn():
             return await self._page.reload(wait_until="domcontentloaded")
        return await self._run_on_main_loop(_fn())

    # --- Native Semantic Helpers ---
    _selector_map = {}

    async def get_snapshot(self, interactive_only: bool = True):
        """Generate a semantic snapshot and populate selector map."""
        async def _snap():
            # clear previous map
            self._selector_map.clear()
            
            # Simple heuristic script to find interactive elements
            js_script = """
            () => {
                const elements = Array.from(document.querySelectorAll('a, button, input, textarea, select, [role="button"], [role="link"]'));
                const visibleElements = elements.filter(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                });
                
                return visibleElements.map((el, index) => {
                    // Generate a simple unique selector if possible, or use index strategy
                    el.setAttribute('data-agent-ref', index);
                    
                    let label = el.innerText || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.value || '';
                    label = label.substring(0, 50).replace(/\\n/g, ' ');
                    
                    return {
                        index: index,
                        tagName: el.tagName.toLowerCase(),
                        type: el.getAttribute('type'),
                        label: label,
                        href: el.getAttribute('href')
                    };
                });
            }
            """
            try:
                items = await self._page.evaluate(js_script)
            except Exception as e:
                logger.error(f"Snapshot script failed: {e}")
                return "Error generating snapshot."
            
            output_lines = []
            for item in items:
                idx = item['index']
                ref = f"@e{idx}"
                self._selector_map[ref] = f"[data-agent-ref='{idx}']"
                
                line = f"{ref}: <{item['tagName']}"
                if item['type']:
                    line += f" type='{item['type']}'"
                if item['href']:
                    line += f" href='{item['href']}'"
                line += f"> {item['label']}"
                output_lines.append(line)
                
            return "\n".join(output_lines) if output_lines else "No interactive elements found."

        return await self._run_on_main_loop(_snap())

    async def interact(self, action: str, ref: str, value: str = None):
        """Interact with an element by ref or selector."""
        async def _act():
            # Resolve ref if it exists
            selector = self._selector_map.get(ref, ref)
            
            try:
                if action == "click":
                    await self._page.click(selector)
                    return f"Clicked {ref}"
                elif action == "dblclick":
                    await self._page.dblclick(selector)
                    return f"Double-clicked {ref}"
                elif action == "fill":
                    await self._page.fill(selector, value or "")
                    return f"Filled {ref} with '{value}'"
                elif action == "type":
                    await self._page.type(selector, value or "")
                    return f"Typed '{value}' into {ref}"
                elif action == "hover":
                    await self._page.hover(selector)
                    return f"Hovered {ref}"
                elif action == "press":
                    # value is key name
                    await self._page.press(selector, value)
                    return f"Pressed '{value}' on {ref}"
                else:
                    return f"Unknown action {action}"
            except Exception as e:
                return f"Interaction failed: {e}"

        return await self._run_on_main_loop(_act())

    async def _on_screencast_frame(self, params):
        """Handle incoming CDP screencast frames."""
        try:
            # Acknowledge the frame so CDP keeps sending them
            await self._client.send("Page.screencastFrameAck", {"sessionId": params.get("sessionId")})
            
            data = params.get("data") # Base64 string
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
                "timestamp": metadata.get("timestamp")
            }
            
            # Broadcast loop
            disconnected = []
            for ws in self._websockets:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            
            # Cleanup disconnected
            for ws in disconnected:
                self._websockets.remove(ws)
                
        except Exception as e:
            logger.error(f"Error handling screencast frame: {e}")

    async def start_streaming(self):
        if self._streaming or not self._client:
            return
        logger.info("Starting CDP Screencast...")
        await self._client.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": 60,
            "maxWidth": 1280,
            "maxHeight": 800,
            "everyNthFrame": 1 # Send every frame
        })
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
        await websocket.accept()
        self._websockets.append(websocket)
        # Ensure streaming is active if we have clients
        if not self._streaming and self._client:
            await self.start_streaming()
        elif not self._client:
             # Lazy init if browser isn't open yet
            await self.ensure_session()
            await self.start_streaming()

    async def remove_client(self, websocket: WebSocket):
        if websocket in self._websockets:
            self._websockets.remove(websocket)
        # If no clients left, maybe stop streaming to save resources?
        if not self._websockets:
            await self.stop_streaming()

    async def handle_client_message(self, message: dict):
        """Process interaction events from the frontend."""
        if not self._page:
            return
            
        action = message.get("type")
        
        try:
            if action == "click":
                x, y = message.get("x"), message.get("y")
                if x is not None and y is not None:
                    await self._page.mouse.click(x, y)
                    
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
                
            elif action == "navigate":
                url = message.get("url")
                if url:
                    await self._page.goto(url)
        except Exception as e:
             logger.error(f"Error handling client browser interaction: {e}")

    async def close_session(self):
        """Clean up browser resources."""
        logger.info("Closing Browser Session...")
        await self.stop_streaming()
        
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.debug(f"Ignored error closing context: {e}")
            self._context = None
            
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                # Common race condition on Ctrl+C: driver dies before we close
                logger.debug(f"Ignored error closing browser (likely already closed): {e}")
            self._browser = None
            
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug(f"Ignored error stopping playwright: {e}")
            self._playwright = None
            
        self._page = None
        self._client = None
        logger.info("Browser Session Closed.")

class BrowsingTool(Tool):
    name = "browsing_tool"
    description = """Browser Tool
    
    Optimal Workflow:
    1. 'open' <url>: Navigate to page.
    2. 'snapshot -i': Returns interactive elements with refs (e.g., @e1, @e2).
    3. 'click @e1' or 'fill @e1 "text"': Interact using the refs.
    
    Commands:
    - open <url>: Navigate to a URL.
    - snapshot [-i]: Get structural snapshot of page. -i for interactive only (recommended).
    - click <selector|ref>: Click element (e.g. click @e1).
    - fill <selector|ref> <text>: Fill input (e.g. fill @e1 "hello").
    - scroll: Scroll down.
    - back / forward / refresh: Navigation.
    - screenshot: Take a screenshot.
    - start_stream: (Internal) Start video stream.
    - click_coords <x> <y>: Click specific coordinates.
    """
    inputs = {
        "command": {
            "type": "string",
            "description": "The command to execute (e.g., open, snapshot, click)."
        },
        "arguments": {
            "type": "array",
            "description": "Optional arguments for the command (e.g., url, selector).",
            "nullable": True
        }
    }
    output_type = "string"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session_mgr = BrowserSessionManager.get_instance()

    async def _execute(self, command: str, arguments: list = None):
        arguments = arguments or []
        
        # Ensure session exists (this also starts CDP if needed)
        await self.session_mgr.ensure_session()
        
        # --- PATH A: NATIVE (System/User Logic) ---
        if command == "open":
            url = arguments[0] if arguments else "about:blank"
            if not url.startswith("http"):
                url = "https://" + url
            try:
                # Use manager wrapper for thread safety
                await self.session_mgr.goto(url)
            except Exception as e:
                return f"Error opening {url} (partial load): {e}"
            return f"Opened {url}"
            
        elif command == "back":
            await self.session_mgr.back()
            return "Navigated back."
            
        elif command == "forward":
            await self.session_mgr.forward()
            return "Navigated forward."
            
        elif command == "reload" or command == "refresh":
            await self.session_mgr.reload()
            return "Reloaded page."
            
        elif command == "click_coords":
            x, y = int(arguments[0]), int(arguments[1])
            # Use manager wrapper for thread safety
            await self.session_mgr.click(x, y)
            return f"Clicked at {x}, {y}"
            
        elif command == "scroll":
            # arguments: [dx, dy] 
            # If simplistic usage: just scroll down
            await self.session_mgr.scroll(0, 500)
            return "Scrolled down."

        # --- PATH B: PYTHON NATIVE SEMANTIC LOGIC (Replacing Agent-Browser CLI) ---
        # The Agent uses 'snapshot' to "reason" about the page (e.g. use @e1 locators)
        # We now handle this natively via Playwright injection for reliability.
        
        if command == "snapshot":
            # arguments like ['-i'] are ignored as we default to interactive for now
            return await self.session_mgr.get_snapshot(interactive_only=True)
            
        elif command in ["click", "dblclick", "hover"]:
             if not arguments: return f"Error: {command} requires a target ref (e.g. {command} @e1)"
             ref = arguments[0]
             return await self.session_mgr.interact(command, ref)
             
        elif command in ["fill", "type"]:
             if not arguments: return f"Error: {command} requires a target ref (e.g. {command} @e1 'text')"
             ref = arguments[0]
             val = arguments[1] if len(arguments) > 1 else ""
             return await self.session_mgr.interact(command, ref, val)
             
        elif command == "press":
             if not arguments: return "Error: press requires ref and key (e.g. press @e1 Enter)"
             ref = arguments[0]
             key = arguments[1] if len(arguments) > 1 else "Enter"
             return await self.session_mgr.interact("press", ref, key)

        return f"Unknown command {command}"

    def forward(self, command: str, arguments: list = None) -> str:
        return asyncio.run(self._execute(command, arguments))
