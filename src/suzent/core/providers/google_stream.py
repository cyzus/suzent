"""Metadata-only diagnostics before Google chunks become model events."""

import time
import uuid
from collections.abc import AsyncIterator

from google.genai.types import GenerateContentResponse
from pydantic_ai.models import ModelRequestParameters, StreamedResponse
from pydantic_ai.models.google import GoogleModel

from suzent.logger import get_logger

logger = get_logger(__name__)


class ObservedGoogleModel(GoogleModel):
    async def _process_streamed_response(
        self,
        response: AsyncIterator[GenerateContentResponse],
        model_request_parameters: ModelRequestParameters,
    ) -> StreamedResponse:
        stream_id = uuid.uuid4().hex

        async def observe() -> AsyncIterator[GenerateContentResponse]:
            previous = time.monotonic()
            count = 0
            try:
                async for chunk in response:
                    now = time.monotonic()
                    count += 1
                    candidates = chunk.candidates or []
                    parts = [
                        part
                        for candidate in candidates
                        if candidate.content
                        for part in candidate.content.parts or []
                    ]
                    logger.debug(
                        "[GoogleStream] stream_id={} response_id={} chunk={} gap_s={:.3f} "
                        "text_parts={} thought_parts={} tool_parts={} finish_reasons={}",
                        stream_id,
                        chunk.response_id,
                        count,
                        now - previous,
                        sum(
                            part.text is not None and not part.thought for part in parts
                        ),
                        sum(bool(part.thought) for part in parts),
                        sum(part.function_call is not None for part in parts),
                        [candidate.finish_reason for candidate in candidates],
                    )
                    previous = now
                    yield chunk
            finally:
                logger.debug(
                    "[GoogleStream] stream_id={} closed chunks={} last_chunk_age_s={:.3f}",
                    stream_id,
                    count,
                    time.monotonic() - previous,
                )
                close = getattr(response, "aclose", None)
                if close is not None:
                    await close()

        return await super()._process_streamed_response(
            observe(), model_request_parameters
        )
