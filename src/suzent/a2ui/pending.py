"""
Pending question registry for ask_question deferred tool.

Stores asyncio Futures keyed by (chat_id, surface_id) so that
ask_question_tool can block waiting for a user response, and the
/canvas/{chat_id}/answer route can resolve it when the user submits.
"""

import asyncio

# Module-level dict — intentionally shared across requests (one event loop)
_PENDING: dict[tuple[str, str], "asyncio.Future[dict]"] = {}


def create(chat_id: str, surface_id: str) -> "asyncio.Future[dict]":
    key = (chat_id, surface_id)
    future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
    _PENDING[key] = future
    return future


def cancel_all() -> None:
    """Cancel all pending futures — called on server shutdown."""
    for key, future in list(_PENDING.items()):
        if not future.done():
            future.cancel()
    _PENDING.clear()


def resolve(chat_id: str, surface_id: str, answer: dict) -> bool:
    """Resolve the pending future. Returns True if one was found."""
    future = _PENDING.pop((chat_id, surface_id), None)
    if future and not future.done():
        future.set_result(answer)
        return True
    return False


def cancel(chat_id: str, surface_id: str) -> None:
    future = _PENDING.pop((chat_id, surface_id), None)
    if future and not future.done():
        future.cancel()
