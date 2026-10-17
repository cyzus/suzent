"""
Input suggestion routes:
- POST /chat/input-suggestion: predict the user's next message
- GET  /chat/input-suggestion?chat_id=...: the prediction saved for a chat

Predicts the user's next message so the composer can show it as ghost text.
The client sends the recent messages it is showing, because the final save of
a turn can land after its stream has already ended. A prediction made for a
chat is saved so any device that opens the chat can show it again.
"""

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.input_suggestion import MAX_CONTEXT_MESSAGES, suggest_next_input
from suzent.database import get_database


class _SuggestionMessage(BaseModel):
    role: str
    content: str | None = None


class _SuggestionRequest(BaseModel):
    messages: list[_SuggestionMessage] = Field(max_length=MAX_CONTEXT_MESSAGES * 4)
    chat_id: str | None = None
    reply_key: str | None = Field(default=None, max_length=64)


async def get_input_suggestion(request: Request) -> JSONResponse:
    """Return ``{"suggestion": str | null}`` for the user's next message."""
    try:
        body = _SuggestionRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    messages = [m.model_dump() for m in body.messages]
    suggestion = await suggest_next_input(messages)
    if body.chat_id and body.reply_key:
        get_database().set_input_suggestion(body.chat_id, body.reply_key, suggestion)
    return JSONResponse({"suggestion": suggestion})


async def get_saved_input_suggestion(request: Request) -> JSONResponse:
    """Return ``{"reply_key": str | null, "suggestion": str | null}`` for a chat."""
    chat_id = request.query_params.get("chat_id")
    if not chat_id:
        return JSONResponse({"error": "chat_id is required"}, status_code=400)

    saved = get_database().get_input_suggestion(chat_id)
    return JSONResponse(
        {
            "reply_key": saved.reply_key if saved else None,
            "suggestion": saved.text if saved else None,
        }
    )
