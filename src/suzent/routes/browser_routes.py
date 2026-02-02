from starlette.websockets import WebSocket
from suzent.logger import get_logger
from suzent.tools.browsing_tool import BrowserSessionManager

logger = get_logger(__name__)

async def browser_websocket_endpoint(websocket: WebSocket):
    session_mgr = BrowserSessionManager.get_instance()
    
    # Accept connection immediately
    await session_mgr.add_client(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            await session_mgr.handle_client_message(data)
    except Exception as e:
        logger.debug(f"WebSocket client disconnected: {e}")
    finally:
        await session_mgr.remove_client(websocket)

