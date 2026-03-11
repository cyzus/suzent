from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
import os

from pydantic import BaseModel


@contextmanager
def _temporary_env(key: str, value: str):
    """Temporarily set an environment variable, restoring the original on exit."""
    original = os.environ.get(key)
    os.environ[key] = value
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original


class Model(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    context_length: Optional[int] = None


def prefixed(provider_id: str, raw: str) -> str:
    """Ensure a model ID has the provider prefix (e.g. 'deepseek/deepseek-chat')."""
    p = f"{provider_id}/"
    return raw if raw.startswith(p) else f"{p}{raw}"


class BaseProvider(ABC):
    def __init__(self, provider_id: str, config: Dict[str, Any]):
        self.provider_id = provider_id
        self.config = config

    @abstractmethod
    async def list_models(self) -> List[Model]:
        """Fetch or return list of available models."""
        pass

    async def validate_credentials(self) -> bool:
        """Check if credentials are valid. Default: succeeds if list_models returns any models."""
        return len(await self.list_models()) > 0
