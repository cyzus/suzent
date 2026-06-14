"""
LiteLLM integration for embeddings and completions.

Provides unified interface for:
- Embedding generation (for memory search)
- LLM completions (for fact extraction, etc.)
"""

from typing import List, Dict, Any, Optional, Type, TypeVar
import asyncio
import json
import os

from pydantic import BaseModel

from suzent.config import CONFIG
from suzent.core.providers.catalog import PROVIDER_REGISTRY_BY_ID
from suzent.core.providers.helpers import resolve_api_key
from suzent.logger import get_logger

logger = get_logger(__name__)


def _litellm():
    import litellm as _ll

    _ll.drop_params = True
    return _ll


def _litellm_model_and_kwargs(
    model: Optional[str],
) -> tuple[Optional[str], Dict[str, str]]:
    """Return LiteLLM model/auth args matching the provider registry."""
    if not model:
        return model, {}

    provider, _, _model_name = model.partition("/")
    if not provider:
        return model, {}

    kwargs: Dict[str, str] = {}
    api_key = resolve_api_key(provider)
    if api_key:
        kwargs["api_key"] = api_key

    spec = PROVIDER_REGISTRY_BY_ID.get(provider)
    litellm_model = model
    if spec:
        base_url = None
        for field in spec.fields:
            env_key = field.get("key", "")
            if "BASE_URL" not in env_key:
                continue
            try:
                from suzent.core.secrets import get_secret_manager

                base_url = get_secret_manager().get(env_key)
            except Exception:
                base_url = None
            if not base_url:
                base_url = os.environ.get(env_key)
            break

        base_url = base_url or spec.base_url
        if base_url:
            kwargs["api_base"] = base_url

        if spec.base_url and spec.api_type == "openai" and _model_name:
            litellm_model = f"openai/{_model_name}"

    return litellm_model, kwargs


def _model_supports_response_schema(model: Optional[str]) -> bool:
    """Return whether configured capabilities allow native response schemas."""
    if not model:
        return True

    try:
        from suzent.core.model_registry import get_model_registry

        caps = get_model_registry().get_capabilities(model)
    except Exception:
        return True

    return True if caps is None else caps.supports_response_schema


def _model_supports_reasoning(model: Optional[str]) -> bool:
    """Return whether configured capabilities allow reasoning params."""
    if not model:
        return False

    try:
        from suzent.core.model_registry import get_model_registry

        caps = get_model_registry().get_capabilities(model)
    except Exception:
        return False

    return caps.supports_reasoning if caps is not None else False


def _parse_json_response(content: str) -> Any:
    """Parse raw or fenced JSON returned by a model."""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return json.loads(stripped)


# Type variable for Pydantic models
T = TypeVar("T", bound=BaseModel)


class EmbeddingGenerator:
    """Generate embeddings for memory content using LiteLLM."""

    def __init__(self, model: str = None, dimension: int = 0):
        """Initialize embedding generator.

        Args:
            model: LiteLLM model identifier. If omitted, resolved from the
                   RoleRouter "embedding" role. Callers should check
                   ``self.model`` before use; pass None means not configured.
            dimension: Expected embedding dimension (0 = auto-detect).
        """
        if model:
            self.model = model
        else:
            try:
                from suzent.core.role_router import get_role_router

                self.model = get_role_router().get_model_id("embedding")
            except Exception:
                self.model = None
        self.dimension = dimension or CONFIG.embedding_dimension
        self.timeout = CONFIG.embedding_timeout

    async def generate(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not self.model:
            raise ValueError(
                "No embedding model configured. Set it in Settings → Model Roles → Embedding."
            )
        if not text or not text.strip():
            return [0.0] * self.dimension

        try:
            model, auth_kwargs = _litellm_model_and_kwargs(self.model)
            # Bound the call so a slow/unreachable provider can't hang memory
            # search forever. timeout= is passed to LiteLLM and the outer
            # wait_for is a backstop in case the provider ignores it.
            response = await asyncio.wait_for(
                _litellm().aembedding(
                    model=model,
                    input=text,
                    timeout=self.timeout,
                    **auth_kwargs,
                ),
                timeout=self.timeout,
            )

            embedding = response.data[0]["embedding"]

            # Auto-detect dimension on first call
            if not self.dimension:
                self.dimension = len(embedding)
                logger.info(
                    f"Auto-detected embedding dimension: {self.dimension} (model={self.model})"
                )

            # Validate dimension match
            if self.dimension != len(embedding):
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self.dimension}, "
                    f"got {len(embedding)} from model={self.model}"
                )

            return embedding

        except Exception as e:
            # Never fabricate a zero vector on failure. A zero vector is a valid-looking
            # but semantically-null point: the store will happily persist it, silently
            # poisoning the index (all-zero rows) and breaking retrieval with no signal.
            # Raise so the caller can skip/retry — the source data stays safe in markdown.
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def generate_batch(
        self, texts: List[str], batch_size: int = 32
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts in batches."""
        if not self.model:
            raise ValueError(
                "No embedding model configured. Set it in Settings → Model Roles → Embedding."
            )
        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            try:
                model, auth_kwargs = _litellm_model_and_kwargs(self.model)
                response = await asyncio.wait_for(
                    _litellm().aembedding(
                        model=model,
                        input=batch,
                        timeout=self.timeout,
                        **auth_kwargs,
                    ),
                    timeout=self.timeout,
                )

                batch_embeddings = [item["embedding"] for item in response.data]
                all_embeddings.extend(batch_embeddings)

            except Exception as e:
                # Don't fabricate zero vectors on failure — that poisons the index.
                # Fail loudly so the caller can skip/retry.
                logger.error(f"Failed to generate batch embeddings: {e}")
                raise

        return all_embeddings


class ImageGenerator:
    """Generate images using LiteLLM."""

    def __init__(self, model: str = None):
        if model:
            self.model = model
        else:
            try:
                from suzent.core.role_router import get_role_router

                self.model = get_role_router().get_model_id("image_generation")
            except Exception:
                self.model = None

    async def generate(self, prompt: str, size: str = "1024x1024") -> str:
        """Generate an image from a prompt.

        Args:
            prompt: Text description of the image
            size: Image dimensions (e.g., "1024x1024")

        Returns:
            URL to the generated image
        """
        try:
            model, auth_kwargs = _litellm_model_and_kwargs(self.model)
            response = await _litellm().aimage_generation(
                prompt=prompt,
                model=model,
                size=size,
                **auth_kwargs,
            )

            data = response.data[0]
            if hasattr(data, "url") and data.url:
                return data.url
            elif hasattr(data, "b64_json") and data.b64_json:
                return f"data:image/png;base64,{data.b64_json}"
            else:
                return None

        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            raise


class LLMClient:
    """LiteLLM client for structured completions with Pydantic model support."""

    def __init__(self, model: str = None):
        """Initialize LLM client.

        Args:
            model: LiteLLM model identifier (defaults to CONFIG default model)
        """
        self.model = model

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        response_format: Optional[Any] = None,
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """Generate completion for a prompt.

        Args:
            prompt: User prompt
            system: Optional system message
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            response_format: Optional response format - can be:
                - Dict like {"type": "json_object"}
                - Pydantic model class for structured output
            reasoning_effort: Optional reasoning budget hint for compatible models

        Returns:
            Generated text response
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        completion_kwargs: Dict[str, Any] = {}
        litellm_model: Optional[str] = None
        try:
            model, auth_kwargs = _litellm_model_and_kwargs(self.model)
            litellm_model = model
            completion_kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **auth_kwargs,
            }
            if response_format is not None:
                completion_kwargs["response_format"] = response_format
            if reasoning_effort is not None and _model_supports_reasoning(self.model):
                completion_kwargs["reasoning_effort"] = reasoning_effort

            response = await _litellm().acompletion(**completion_kwargs)

            return response.choices[0].message.content

        except Exception as e:
            retry_error = e
            for param_name in (
                "reasoning_effort",
                "response_format",
                "max_tokens",
                "temperature",
            ):
                if param_name not in completion_kwargs:
                    continue
                logger.warning(
                    f"LLM completion with {param_name} failed for model={self.model!r} "
                    f"(litellm_model={litellm_model!r}), retrying without it: {retry_error}"
                )
                completion_kwargs.pop(param_name, None)
                try:
                    response = await _litellm().acompletion(**completion_kwargs)
                    return response.choices[0].message.content
                except Exception as current_error:
                    retry_error = current_error

            if system and completion_kwargs:
                logger.warning(
                    f"LLM completion with system message failed for model={self.model!r} "
                    f"(litellm_model={litellm_model!r}), retrying as user-only message: {retry_error}"
                )
                completion_kwargs["messages"] = [
                    {"role": "user", "content": f"{system}\n\n{prompt}"}
                ]
                try:
                    response = await _litellm().acompletion(**completion_kwargs)
                    return response.choices[0].message.content
                except Exception as current_error:
                    retry_error = current_error

            logger.error(
                f"LLM completion failed for model={self.model!r} "
                f"(litellm_model={litellm_model!r}): {retry_error}"
            )
            raise retry_error

    async def extract_with_schema(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        temperature: float = 0.3,
    ) -> T:
        """Extract structured data using a Pydantic model schema.

        Uses LiteLLM's built-in support for Pydantic models to enforce
        structured output from the LLM.

        Args:
            prompt: User prompt
            response_model: Pydantic model class defining the expected output schema
            system: Optional system message
            temperature: Sampling temperature (lower for more deterministic)
            max_tokens: Maximum tokens to generate

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If response cannot be validated against the model
        """
        if not _model_supports_response_schema(self.model):
            logger.debug(
                f"Model {self.model} does not advertise response schema support; using JSON prompt fallback"
            )
            return await self._extract_with_prompt_json(
                prompt=prompt,
                response_model=response_model,
                system=system,
                temperature=temperature,
            )

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            model, auth_kwargs = _litellm_model_and_kwargs(self.model)
            # Use Pydantic model directly as response_format
            # LiteLLM converts this to json_schema format automatically
            response = await _litellm().acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_model,
                **auth_kwargs,
            )

            content = response.choices[0].message.content

            # Validate and parse with Pydantic
            return response_model.model_validate_json(content)

        except Exception as e:
            logger.warning(
                f"Structured extraction failed, retrying with JSON prompt fallback: {e}"
            )
            try:
                return await self._extract_with_prompt_json(
                    prompt=prompt,
                    response_model=response_model,
                    system=system,
                    temperature=temperature,
                )
            except Exception as retry_error:
                logger.error(f"Structured extraction failed: {retry_error}")
                raise ValueError(
                    f"Failed to extract structured data: {retry_error}"
                ) from retry_error

    async def _extract_with_prompt_json(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str],
        temperature: float,
    ) -> T:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        json_prompt = (
            f"{prompt}\n\n"
            "Return only valid JSON matching this JSON schema. "
            "Do not include markdown fences or explanatory text.\n"
            f"{schema}"
        )
        content = await self.complete(
            prompt=json_prompt,
            system=system,
            temperature=temperature,
            max_tokens=2000,
        )
        return response_model.model_validate(_parse_json_response(content))

    async def extract_structured(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.3,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> Dict[str, Any]:
        """Extract structured JSON data from prompt.

        Args:
            prompt: User prompt
            system: Optional system message
            temperature: Sampling temperature (lower for more deterministic)
            response_model: Optional Pydantic model for schema enforcement

        Returns:
            Parsed JSON object (or dict from validated Pydantic model)

        Raises:
            ValueError: If response is not valid JSON
        """
        # If a Pydantic model is provided, use schema-based extraction
        if response_model is not None:
            result = await self.extract_with_schema(
                prompt=prompt,
                response_model=response_model,
                system=system,
                temperature=temperature,
            )
            return result.model_dump()

        # Fallback to basic JSON mode
        response = await self.complete(
            prompt=prompt,
            system=system,
            temperature=temperature,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        try:
            return _parse_json_response(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"LLM returned invalid JSON: {e}")
