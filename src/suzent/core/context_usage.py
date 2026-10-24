"""Source-aware estimates of the context actually prepared for a model request."""

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import WrapModelRequestHandler
from pydantic_ai.messages import ModelMessage, ModelResponse, TextContent
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters

from suzent.core.agent_deps import AgentDeps
from suzent.logger import get_logger

logger = get_logger(__name__)

type Category = Literal[
    "messages",
    "tool_results",
    "system_tools",
    "mcp_tools",
    "system_prompt",
    "skills",
    "memory",
    "repository",
    "other",
]


class ContextSource(BaseModel):
    category: Category
    name: str


class ContextItem(BaseModel):
    name: str
    tokens: int = Field(ge=0)


class ContextCategory(BaseModel):
    id: Category
    tokens: int = Field(ge=0)
    items: list[ContextItem]


class ContextBreakdown(BaseModel):
    method: Literal["character_estimate"] = "character_estimate"
    categories: list[ContextCategory]
    deferred: list[ContextCategory]
    estimated_tokens: int = Field(ge=0)
    reserve_tokens: int = Field(ge=0)
    measured_input_tokens: int | None = None
    #: Text estimate of instructions and tool schemas, used before calibration.
    overhead_estimate: int = Field(default=0, ge=0)
    has_unmeasured_media: bool = False


def source_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def register_context_source(
    deps: AgentDeps, text: str, category: Category, name: str
) -> str:
    if text:
        if not hasattr(deps, "context_sources"):
            deps.context_sources = {}
        deps.context_sources[source_key(text)] = ContextSource(
            category=category, name=name
        ).model_dump()
    return text


# CJK ideographs, kana, hangul and full-width forms: current tokenizers spend
# roughly 0.7-1.3 tokens on each, so one per character sits in the middle.
_CJK = re.compile(
    "[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
    "\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]"
)


def estimate_text(text: str) -> int:
    """Approximate token count, weighting scripts by how densely they tokenize."""
    if text.isascii():
        return math.ceil(len(text) / 4)
    cjk = len(_CJK.findall(text))
    other = sum(1 for char in text if not char.isascii()) - cjk
    ascii_chars = len(text) - cjk - other
    return math.ceil(cjk + other * 0.5 + ascii_chars * 0.25)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def build_context_breakdown(
    messages: list[ModelMessage],
    parameters: ModelRequestParameters,
    sources: dict[str, dict[str, str]],
    limit: int,
    trigger: float,
    measured_input_tokens: int | None = None,
) -> ContextBreakdown:
    from suzent.core.context_compressor import estimate_tokens

    buckets: dict[Category, dict[str, int]] = {}
    deferred: dict[Category, dict[str, int]] = {}
    has_media = False

    def add(category: Category, name: str, text: str, *, hidden: bool = False) -> None:
        if not text:
            return
        group = (deferred if hidden else buckets).setdefault(category, {})
        group[name] = group.get(name, 0) + estimate_text(text)

    def add_text(
        text: str, category: Category, name: str, provenance: dict[str, Any]
    ) -> None:
        from suzent.core.system_reminder import iter_reminder_fragments

        source = provenance.get(source_key(text))
        if source:
            parsed = ContextSource.model_validate(source)
            if parsed.category == "memory" and parsed.name == "core_memory":
                core = re.search(
                    r"## Core Memory \(Always Visible\)\n.*?\n"
                    r"(?P<blocks>\*\*(?:Persona|User|Context|Memory|Facts)\*\*:.*?)"
                    r"\n## Archival Memory \(Search When Needed\)",
                    text,
                    re.DOTALL,
                )
                if core:
                    blocks = core.group("blocks")
                    matches = list(
                        re.finditer(
                            r"^\*\*(Persona|User|Context|Memory|Facts)\*\*:\n",
                            blocks,
                            re.MULTILINE,
                        )
                    )
                    names = {
                        "Persona": "persona.md",
                        "User": "user.md",
                        "Memory": "MEMORY.md",
                        "Facts": "MEMORY.md",
                        "Context": "project_context",
                    }
                    for index, block in enumerate(matches):
                        end = (
                            matches[index + 1].start()
                            if index + 1 < len(matches)
                            else len(blocks)
                        )
                        add(
                            "memory", names[block.group(1)], blocks[block.start() : end]
                        )
                    add(
                        "memory",
                        "memory_instructions",
                        text[: core.start("blocks")] + text[core.end("blocks") :],
                    )
                    return
            if parsed.category == "repository":
                # RepoContext renders labeled blocks. Parse only output whose
                # exact digest was registered by that capability, never user text.
                blocks = list(
                    re.finditer(
                        r'<context-file path="([^"]+)">\n.*?\n</context-file>',
                        text,
                        re.DOTALL,
                    )
                )
                if blocks:
                    for block in blocks:
                        add("repository", block.group(1), block.group(0))
                    remainder = re.sub(
                        r'<context-file path="([^"]+)">\n.*?\n</context-file>',
                        "",
                        text,
                        flags=re.DOTALL,
                    )
                    if remainder.strip():
                        add("repository", parsed.name, remainder)
                    return
            add(parsed.category, parsed.name, text)
            return
        # Only recorded, exact fragments are reattributed; ordinary user text is
        # never classified from headings or filenames it happens to contain.
        for block in iter_reminder_fragments(text):
            for fragment in block:
                source = provenance.get(source_key(fragment.strip()))
                if source:
                    parsed = ContextSource.model_validate(source)
                    add(parsed.category, parsed.name, fragment.strip())
                    text = text.replace(fragment.strip(), "", 1)
        add(category, name, text)

    skill_calls: dict[str, str] = {}
    for message in messages:
        provenance = (message.metadata or {}).get("context_sources", {})
        for part in message.parts:
            kind = part.part_kind
            if kind == "system-prompt":
                add_text(part.content, "system_prompt", "system_prompt", provenance)
            elif kind in ("tool-call", "tool-return", "retry-prompt"):
                name = getattr(part, "tool_name", None) or "tool_results"
                category: Category = (
                    "skills" if name == "skill_execute" else "tool_results"
                )
                content = getattr(part, "content", None)
                if kind == "tool-call":
                    content = part.args
                    if name == "skill_execute":
                        try:
                            args = part.args_as_dict()
                            skill_calls[part.tool_call_id] = str(
                                args.get("skill_name") or name
                            )
                        except (ValueError, TypeError):
                            pass
                elif kind == "tool-return":
                    content, media = part.model_response_str_and_user_content()
                    has_media = has_media or bool(media)
                if name == "skill_execute":
                    name = skill_calls.get(part.tool_call_id, name)
                add(category, name, _text(content))
            elif kind in ("user-prompt", "text", "thinking"):
                content = part.content
                if isinstance(content, str):
                    add_text(content, "messages", kind, provenance)
                elif isinstance(content, (list, tuple)):
                    for item in content:
                        if isinstance(item, (str, TextContent)):
                            add_text(
                                item if isinstance(item, str) else item.content,
                                "messages",
                                kind,
                                provenance,
                            )
                        else:
                            has_media = True
            elif kind != "tool-availability-delta":
                # Native tool search/results and provider-specific parts still
                # occupy history; binary media must not be counted as base64 text.
                content = getattr(part, "content", None)
                if isinstance(content, str):
                    add("other", kind, content)
                else:
                    has_media = True

    history_rows = sum(sum(items.values()) for items in buckets.values())
    for instruction in parameters.instruction_parts or []:
        add_text(instruction.content, "system_prompt", "system_prompt", sources)

    for tool in [*parameters.function_tools, *parameters.output_tools]:
        category = (
            "mcp_tools"
            if (tool.metadata or {}).get("suzent_context_source") == "mcp"
            else "system_tools"
        )
        visibility = parameters.visibility_of(tool.name)
        add(
            category,
            tool.name,
            _text(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_json_schema,
                }
            ),
            hidden=visibility in ("withheld", "deferred"),
        )
    if parameters.native_tools or parameters.output_object:
        # Provider-owned schemas and media encoding are not exposed as text.
        has_media = True

    raw_total = sum(sum(items.values()) for items in buckets.values())
    # The headline is the calibrated estimate the compaction trigger uses; the
    # rows are scaled to it so the bar still adds up to the number shown.
    estimated = estimate_tokens(
        messages, limit, fallback_overhead=raw_total - history_rows
    ).estimated_tokens
    scale = estimated / raw_total if raw_total else 1.0

    def categories(
        values: dict[Category, dict[str, int]], factor: float = 1.0
    ) -> list[ContextCategory]:
        rows = []
        for key, items in values.items():
            scaled = [
                ContextItem(name=name, tokens=round(tokens * factor))
                for name, tokens in sorted(items.items(), key=lambda item: -item[1])
            ]
            rows.append(
                ContextCategory(
                    id=key, tokens=sum(item.tokens for item in scaled), items=scaled
                )
            )
        return rows

    return ContextBreakdown(
        categories=categories(buckets, scale),
        deferred=categories(deferred),
        estimated_tokens=estimated,
        overhead_estimate=raw_total - history_rows,
        reserve_tokens=round(limit * (1 - max(0, min(1, trigger)))),
        measured_input_tokens=measured_input_tokens,
        has_unmeasured_media=has_media,
    )


@dataclass
class ContextUsageCapability(AbstractCapability[AgentDeps]):
    model_id: str

    async def wrap_model_request(
        self,
        ctx: RunContext[AgentDeps],
        *,
        request_context: ModelRequestContext,
        handler: WrapModelRequestHandler,
    ) -> ModelResponse:
        if ctx.deps.stateless:
            return await handler(request_context)

        from suzent.config import CONFIG
        from suzent.core.context_compressor import (
            emit_context_usage_event,
            resolve_context_limit,
        )

        limit = resolve_context_limit(self.model_id)

        def publish(response: ModelResponse | None = None) -> None:
            try:
                # Resolve visibility on a copy; never alter the model request.
                _, parameters = request_context.model.prepare_request(
                    request_context.model_settings,
                    deepcopy(request_context.model_request_parameters),
                )
                messages = list(request_context.messages)
                if response is not None:
                    messages.append(response)
                breakdown = build_context_breakdown(
                    messages,
                    parameters,
                    ctx.deps.context_sources,
                    limit,
                    CONFIG.context_compaction_trigger,
                    response.usage.input_tokens if response is not None else None,
                )
                ctx.deps.context_breakdown = breakdown.model_dump()
                ctx.deps.context_overhead_estimate = breakdown.overhead_estimate
                emit_context_usage_event(
                    chat_id=ctx.deps.chat_id,
                    context_tokens=breakdown.estimated_tokens,
                    usage=ctx.usage,
                    context_limit=limit,
                    context_breakdown=ctx.deps.context_breakdown,
                )
            except Exception as exc:
                # Optional diagnostics must never prevent a model request.
                logger.debug("Context breakdown unavailable: {}", type(exc).__name__)
                ctx.deps.context_breakdown = None

        publish()
        response = await handler(request_context)
        publish(response)
        return response
