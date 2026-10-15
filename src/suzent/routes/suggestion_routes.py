"""
Input suggestion route: POST /chat/input-suggestion

Predicts the user's next message so the composer can show it as ghost text.
The client sends the recent messages it is showing, because the final save of
a turn can land after its stream has already ended.
"""

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.core.input_suggestion import MAX_CONTEXT_MESSAGES, suggest_next_input


class _SuggestionMessage(BaseModel):
    role: str
    content: str | None = None


class _SuggestionRequest(BaseModel):
    messages: list[_SuggestionMessage] = Field(max_length=MAX_CONTEXT_MESSAGES * 4)


async def get_input_suggestion(request: Request) -> JSONResponse:
    """Return ``{"suggestion": str | null}`` for the user's next message."""
    try:
        body = _SuggestionRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        return JSONResponse({"error": "Invalid request"}, status_code=400)

    messages = [m.model_dump() for m in body.messages]
    return JSONResponse({"suggestion": await suggest_next_input(messages)})
