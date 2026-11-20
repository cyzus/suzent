"""Decide how a chat run recovers when its model request fails.

A turn used to end at the first provider hiccup: a connection that dropped
halfway through a long reply, a 429, a 503. This module sorts those failures
into kinds, says which are worth another attempt and how long to wait first.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    """What went wrong with a model request, as far as the user is concerned."""

    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    AUTH = "auth"
    QUOTA = "quota"
    NOT_FOUND = "not_found"
    CONTEXT = "context"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


# The same request can succeed a moment later.
TRANSIENT_KINDS = frozenset(
    {
        FailureKind.TIMEOUT,
        FailureKind.CONNECTION,
        FailureKind.RATE_LIMIT,
        FailureKind.OVERLOADED,
    }
)

# Run error codes the frontend localizes. `model_stalled` predates this module
# and sub-agents key their own resume on it, so timeouts and dropped
# connections keep it.
_RUN_ERROR_CODES: dict[FailureKind, str] = {
    FailureKind.TIMEOUT: "model_stalled",
    FailureKind.CONNECTION: "model_stalled",
    FailureKind.RATE_LIMIT: "model_rate_limited",
    FailureKind.OVERLOADED: "model_overloaded",
    FailureKind.AUTH: "model_auth",
    FailureKind.QUOTA: "model_quota",
    FailureKind.NOT_FOUND: "model_not_found",
    FailureKind.CONTEXT: "model_context_exceeded",
}

# Seconds to wait before each retry of the same model.
RETRY_DELAYS_SECONDS: tuple[float, ...] = (2.0, 5.0, 15.0)
# A provider asking us to wait longer than this will not be back mid-turn.
MAX_RETRY_AFTER_SECONDS = 60.0


@dataclass(frozen=True)
class ModelFailure:
    kind: FailureKind
    detail: str
    retry_after: float | None = None

    @property
    def transient(self) -> bool:
        return self.kind in TRANSIENT_KINDS

    @property
    def run_error_code(self) -> str | None:
        return _RUN_ERROR_CODES.get(self.kind)


def _type_names(error: BaseException) -> set[str]:
    names: set[str] = set()
    current: BaseException | None = error
    while current is not None and len(names) < 64:
        names.update(cls.__name__ for cls in type(current).__mro__)
        current = current.__cause__
    return names


def _provider_message(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    nested = body.get("error")
    if isinstance(nested, dict):
        body = nested
    elif isinstance(nested, str) and nested.strip():
        return nested.strip()
    message = body.get("message")
    return message.strip() if isinstance(message, str) and message.strip() else None


def failure_detail(error: BaseException) -> str:
    """A short description of a failure, without the provider's raw error body."""
    status = getattr(error, "status_code", None)
    message = _provider_message(getattr(error, "body", None))
    if isinstance(status, int):
        return f"HTTP {status}: {message}" if message else f"HTTP {status}"
    return message or str(error) or type(error).__name__


def classify_model_failure(error: BaseException) -> ModelFailure | None:
    """Sort a run failure into a kind, or return None if it is not the model's."""
    from pydantic_ai import exceptions as ex

    detail = failure_detail(error)
    retry_after = getattr(error, "retry_after", None)
    if not isinstance(retry_after, int | float) or retry_after < 0:
        retry_after = None

    def failure(kind: FailureKind) -> ModelFailure:
        return ModelFailure(kind=kind, detail=detail, retry_after=retry_after)

    # Order matters: categories nest (a timeout is a connection error, an
    # authentication error is a rejected request).
    if isinstance(error, ex.ModelTimeoutError | ex.ModelRequestTimeout | TimeoutError):
        return failure(FailureKind.TIMEOUT)
    if isinstance(error, ex.ModelConnectionError):
        return failure(FailureKind.CONNECTION)
    if isinstance(error, ex.ModelRateLimitError):
        return failure(FailureKind.RATE_LIMIT)
    if isinstance(error, ex.ModelQuotaExceededError):
        return failure(FailureKind.QUOTA)
    if isinstance(error, ex.ModelUnavailableError | ex.ModelServerError):
        return failure(FailureKind.OVERLOADED)
    if isinstance(error, ex.ModelAuthenticationError):
        return failure(FailureKind.AUTH)
    if isinstance(error, ex.ModelNotFoundError):
        return failure(FailureKind.NOT_FOUND)
    if isinstance(error, ex.ModelContextWindowExceededError):
        return failure(FailureKind.CONTEXT)
    if isinstance(error, ex.ModelHTTPError):
        status = error.status_code
        if status == 429:
            return failure(FailureKind.RATE_LIMIT)
        if status in (401, 403):
            return failure(FailureKind.AUTH)
        if status == 402:
            return failure(FailureKind.QUOTA)
        if status == 404:
            return failure(FailureKind.NOT_FOUND)
        if status in (408, 409) or status >= 500:
            return failure(FailureKind.OVERLOADED)
        return failure(FailureKind.REJECTED)
    if isinstance(error, ex.ModelRequestRejectedError):
        return failure(FailureKind.REJECTED)

    # A stream that broke below the SDK can surface as the transport's own
    # error rather than a pydantic-ai one. Matched by name so this module
    # does not import every provider SDK.
    names = _type_names(error)
    if names & {"APITimeoutError", "ReadTimeout", "ConnectTimeout", "TimeoutException"}:
        return failure(FailureKind.TIMEOUT)
    if names & {
        "APIConnectionError",
        "RemoteProtocolError",
        "ReadError",
        "ConnectError",
        "TransportError",
        "ConnectionError",
        "IncompleteRead",
    }:
        return failure(FailureKind.CONNECTION)
    if isinstance(error, ex.ModelAPIError):
        return failure(FailureKind.UNKNOWN)
    return None


def retry_delay(failure: ModelFailure, attempt: int) -> float | None:
    """Seconds to wait before retry number ``attempt`` (from 1), or None to stop."""
    if not failure.transient or attempt > len(RETRY_DELAYS_SECONDS):
        return None
    delay = RETRY_DELAYS_SECONDS[attempt - 1]
    if failure.retry_after is not None:
        if failure.retry_after > MAX_RETRY_AFTER_SECONDS:
            return None
        delay = max(delay, failure.retry_after)
    return delay
