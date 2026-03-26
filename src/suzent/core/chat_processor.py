"""
Chat Processor: Unified logic for handling conversation turns.

Uses pydantic-ai Agent with async streaming, dependency injection via
AgentDeps, and message-history-based state persistence.
"""

import json
import os
import shutil
import time
from pathlib import Path
from typing import AsyncGenerator, List, Dict, Any, Optional

from suzent.logger import get_logger
from suzent.config import CONFIG, get_effective_volumes
from suzent.agent_manager import get_or_create_agent

from suzent.core.context_injection import build_agent_deps
from suzent.core.agent_serializer import serialize_state, deserialize_state
from suzent.core.context_compressor import ContextCompressor
from suzent.memory.lifecycle import get_memory_manager
from suzent.streaming import stream_agent_responses
from suzent.memory import ConversationTurn, Message, AgentAction
from suzent.database import get_database
from suzent.tools.path_resolver import PathResolver
from suzent.routes.sandbox_routes import sanitize_filename
from suzent.core.stream_parser import StreamParser, TextChunk, ErrorEvent
from suzent.core.stream_registry import pop_pending_auto_approvals


logger = get_logger(__name__)


def _resolve_target_path(host_path: Path, filename: str) -> Path:
    """
    Resolve a safe target path, appending a timestamp suffix on collision.
    """
    target = host_path / filename
    if target.exists():
        target = host_path / f"{target.stem}_{int(time.time() * 1000)}{target.suffix}"
    return target


class ChatProcessor:
    """Encapsulates the lifecycle of a single conversation turn."""

    async def process_turn(
        self,
        chat_id: str,
        user_id: str,
        message_content: str,
        files: List[Any] = None,
        config_override: Dict = None,
        is_social: bool = False,
        resume_approvals: List[Dict] = None,
        is_heartbeat: bool = False,
        _message_history_override: list = None,
    ) -> AsyncGenerator[str, None]:
        """
        Process a user message turn:
        1. Context & Agent Setup
        2. Attachment Processing
        3. Response Streaming (pydantic-ai async)
        4. Background Tasks (Memory, Compression, Persistence)
        """

        # 1. Configuration
        logger.debug(f"[ChatProcessor] Starting process_turn for chat_id={chat_id}")
        config = {
            "_user_id": user_id,
            "_chat_id": chat_id,
            "memory_enabled": CONFIG.memory_enabled,
        }
        if config_override:
            config.update(config_override)

        # 2. Get Agent
        logger.debug("[ChatProcessor] Calling get_or_create_agent")
        try:
            agent = await get_or_create_agent(config)
            logger.debug(f"[ChatProcessor] Agent obtained: {type(agent)}")
        except Exception as e:
            logger.error(f"[ChatProcessor] get_or_create_agent failed: {e}")
            raise

        # 3. Build AgentDeps (replaces inject_chat_context)
        deps = build_agent_deps(chat_id=chat_id, user_id=user_id, config=config)

        # 4. Restore message history from DB (or use override for steer)
        message_history = _message_history_override
        if message_history is None:
            try:
                db = get_database()
                chat = db.get_chat(chat_id)
                if chat and chat.agent_state:
                    state = deserialize_state(chat.agent_state)
                    if state and state.get("message_history"):
                        message_history = state["message_history"]
                        logger.debug(
                            f"Restored {len(message_history)} messages for chat {chat_id}"
                        )
            except Exception as e:
                logger.error(f"Error restoring message history: {e}")

        # 5. Attachment Handling
        agent_images = []
        attachment_context = ""

        if files:
            logger.debug(f"[ChatProcessor] Processing {len(files)} files")
            try:
                custom_volumes = get_effective_volumes([])
                sandbox_enabled = config.get("sandbox_enabled", CONFIG.sandbox_enabled)
                resolver = PathResolver(
                    chat_id=chat_id,
                    sandbox_enabled=sandbox_enabled,
                    custom_volumes=custom_volumes,
                )

                if sandbox_enabled:
                    uploads_virtual_path = "/persistence/uploads"
                else:
                    uploads_virtual_path = str(
                        Path(CONFIG.workspace_root) / "uploads"
                    ).replace("\\", "/")

                uploads_host_path = resolver.resolve(uploads_virtual_path)
                uploads_host_path.mkdir(parents=True, exist_ok=True)

                for file_item in files:
                    if isinstance(file_item, dict):
                        if "mime_type" in file_item:
                            # It's an AG-UI pre-uploaded file
                            v_path = file_item.get("path")
                            result = {
                                "final_path": str(resolver.resolve(v_path))
                                if v_path
                                else None,
                                "virtual_path": v_path,
                                "filename": file_item.get("filename"),
                                "is_image": file_item.get("mime_type", "").startswith(
                                    "image/"
                                ),
                            }
                        else:
                            # It's a social tool attachment
                            result = self._process_social_attachment(
                                file_item, uploads_host_path, uploads_virtual_path
                            )
                    else:
                        result = await self._process_upload_file(
                            file_item, uploads_host_path, uploads_virtual_path
                        )

                    if result["is_image"]:
                        try:
                            # pydantic-ai uses BinaryContent for images
                            from pydantic_ai import BinaryContent

                            with open(result["final_path"], "rb") as f:
                                image_data = f.read()
                            ext = Path(result["final_path"]).suffix.lstrip(".")
                            media_type = f"image/{ext}" if ext else "image/png"
                            agent_images.append(
                                BinaryContent(data=image_data, media_type=media_type)
                            )
                            attachment_context += (
                                f"\n[User attached an image: {result['virtual_path']}]"
                            )
                        except Exception as e:
                            logger.error(f"Failed to load image: {e}")
                            attachment_context += f"\n[Failed to load attached image: {result.get('filename')}]"
                    elif result["virtual_path"]:
                        attachment_context += (
                            f"\n[User attached a file: {result['virtual_path']}]"
                        )

            except Exception as e:
                logger.error(f"Failed to process attachments: {e}")
                attachment_context += "\n[System Error: Failed to process attachments]"

        # 6. Prepare Prompt or Resume
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        if message_history is None:
            message_history = []

        # Universal slash command dispatch (before history is modified or agent runs)
        if message_content and not resume_approvals and not files and not is_heartbeat:
            from suzent.core.commands import (
                dispatch as _dispatch_command,
                CommandContext as _CmdCtx,
            )

            cmd_result = await _dispatch_command(
                _CmdCtx(chat_id=chat_id, user_id=user_id), message_content
            )
            if cmd_result is not None:
                import uuid
                from ag_ui.core import (
                    RunStartedEvent,
                    RunFinishedEvent,
                    TextMessageStartEvent,
                    TextMessageContentEvent,
                    TextMessageEndEvent,
                )
                from ag_ui.encoder import EventEncoder as _Enc

                _enc = _Enc()
                run_id = str(uuid.uuid4())
                msg_id = str(uuid.uuid4())
                yield _enc.encode(RunStartedEvent(run_id=run_id, thread_id=chat_id))
                yield _enc.encode(
                    TextMessageStartEvent(message_id=msg_id, role="assistant")
                )
                yield _enc.encode(
                    TextMessageContentEvent(message_id=msg_id, delta=cmd_result)
                )
                yield _enc.encode(TextMessageEndEvent(message_id=msg_id))
                yield _enc.encode(RunFinishedEvent(run_id=run_id, thread_id=chat_id))
                yield "data: [DONE]\n\n"
                return

        # Only append a new user message if there's actual content or attachments
        # (For stateless resume, we might just be submitting tool results)
        full_prompt = ""
        if message_content or files:
            full_prompt = message_content + attachment_context
            if agent_images:
                content = [full_prompt, *agent_images]
            else:
                content = full_prompt
            parts = [UserPromptPart(content=content)]
            new_request = ModelRequest(parts=parts)
            message_history.append(new_request)

            # Pre-save the user message to the DB display log for social chats so the
            # frontend can show it as soon as the stream starts, without waiting for the
            # background post-processing task that normally persists the full history.
            if (
                chat_id
                and chat_id.startswith("social-")
                and isinstance(full_prompt, str)
                and full_prompt.strip()
            ):
                try:
                    _db = get_database()
                    _chat = _db.get_chat(chat_id)
                    if _chat is not None:
                        _existing = list(_chat.messages or [])
                        _user_entry: dict = {"role": "user", "content": full_prompt}
                        _db.update_chat(chat_id, messages=_existing + [_user_entry])
                except Exception:
                    pass  # Non-fatal; post-processing will persist the full history anyway

        # Handle stateless resume
        deferred_tool_results = None
        if resume_approvals:
            from pydantic_ai.tools import DeferredToolResults

            approvals_dict = {}
            # Include policy-decided approvals cached when a previous stream
            # paused with a mixed auto/user approval batch.
            cached_auto = pop_pending_auto_approvals(chat_id)
            if cached_auto:
                approvals_dict.update(cached_auto)
            for app in resume_approvals:
                tool_call_id = app.get("tool_call_id") or app.get("request_id")
                if tool_call_id:
                    approvals_dict[tool_call_id] = bool(app.get("approved"))

            if approvals_dict:
                deferred_tool_results = DeferredToolResults(approvals=approvals_dict)

                # Also handle 'remember: session' policy updates
                for app in resume_approvals:
                    if app.get("remember") == "session" and app.get("tool_name"):
                        tool_name = app["tool_name"]
                        approved = bool(app.get("approved"))
                        deps.tool_approval_policy[tool_name] = (
                            "always_allow" if approved else "always_deny"
                        )
        else:
            # New user turn (not resume): clear any stale cached auto approvals.
            pop_pending_auto_approvals(chat_id)

        logger.debug(
            f"[ChatProcessor] Prompt prepared. Length: {len(full_prompt)}. Streaming..."
        )

        # 7. Pre-send tool result trimming (in-memory only, never persisted)
        from suzent.core.context_compressor import ToolResultTrimmer, estimate_tokens
        from suzent.config import CONFIG as _cfg

        _budget = estimate_tokens(message_history or [], _cfg.max_context_tokens)
        if _budget.over_hard:
            message_history = ToolResultTrimmer.apply_hard_clear(
                message_history, _budget
            )
        elif _budget.over_soft:
            message_history = ToolResultTrimmer.apply_soft_trim(
                message_history, _budget
            )

        # 8. Stream Response
        full_response = ""

        try:
            async for chunk in stream_agent_responses(
                agent,
                None,
                deps=deps,
                message_history=message_history,
                chat_id=chat_id,
                deferred_tool_results=deferred_tool_results,
                is_heartbeat=is_heartbeat,
            ):
                try:
                    if chunk.startswith("data: "):
                        json_str = chunk[6:].strip()
                        if json_str == "[DONE]":
                            continue
                        event_data = json.loads(json_str)

                        msg_type = event_data.get("type")
                        if msg_type == "TEXT_MESSAGE_CONTENT":
                            full_response += event_data.get("delta", "")
                except Exception:
                    pass

                yield chunk
        finally:
            # 9. Post-Processing (Background)
            # We use a background task so the SSE stream can close immediately
            # while heavy extraction/persistence runs.
            import asyncio
            from suzent.core.task_registry import register_background_task

            async def _run_post_processing() -> None:
                try:
                    # Get the messages from the agent or deps for persistence
                    last_messages = getattr(deps, "last_messages", None)
                    if last_messages is None:
                        last_messages = getattr(agent, "_last_messages", [])

                    # If the stream was interrupted, pydantic-ai does not emit the final ModelResponse.
                    # We manually append the text generated so far so the agent remembers its interrupted thought.
                    is_cancelled = (
                        getattr(deps, "cancel_event", None)
                        and deps.cancel_event.is_set()
                    )
                    if is_cancelled and full_response.strip() and last_messages:
                        from pydantic_ai.messages import ModelResponse, TextPart

                        if not isinstance(last_messages[-1], ModelResponse):
                            logger.debug(
                                f"[ChatProcessor] Stream was cancelled. Appending partial text to history: {len(full_response)} chars"
                            )
                            last_messages.append(
                                ModelResponse(
                                    parts=[TextPart(content=full_response.strip())]
                                )
                            )

                    msg_count = len(last_messages) if last_messages else 0
                    logger.debug(
                        f"[ChatProcessor] Starting background post-processing for {chat_id}. "
                        f"History length: {msg_count}"
                    )

                    # A. Write JSONL transcript
                    await self._write_transcript(
                        chat_id, message_content, full_response, last_messages
                    )

                    is_suspended = getattr(deps, "is_suspended", False)

                    if not is_suspended:
                        # B. Memory Extraction
                        await self._extract_memories(
                            chat_id=chat_id,
                            user_id=user_id,
                            user_content=message_content,
                            agent_content=full_response,
                            messages=last_messages,
                        )

                        # C. Context Compression
                        compressor = ContextCompressor(chat_id=chat_id, user_id=user_id)
                        compressed_messages = await compressor.compress_messages(
                            last_messages
                        )
                    else:
                        logger.debug(
                            f"[ChatProcessor] Skipping memory extraction and compression for suspended run {chat_id}."
                        )
                        compressed_messages = last_messages

                    # D. State Persistence
                    await self._persist_state(
                        chat_id=chat_id,
                        messages=compressed_messages,
                        model_id=getattr(agent, "_model_id", None),
                        tool_names=getattr(agent, "_tool_names", []),
                        user_content=message_content,
                        agent_content=full_response,
                        skip_messages=is_heartbeat,
                    )
                    logger.info(
                        f"[ChatProcessor] Background post-processing complete for {chat_id}"
                    )
                except Exception as e:
                    logger.error(f"Post-processing background task failed: {e}")

            # Register the background task with the global registry
            try:
                await register_background_task(
                    _run_post_processing(),
                    task_id=f"post_process_{chat_id}_{int(time.time())}",
                    description=f"Post-processing for chat {chat_id}",
                )
            except RuntimeError as e:
                logger.warning(f"Failed to register background task: {e}")
                # Fallback to fire-and-forget if registry is full
                asyncio.create_task(_run_post_processing())

    async def process_steer(
        self,
        chat_id: str,
        user_id: str,
        steer_message: str,
        config_override: Dict = None,
    ) -> AsyncGenerator[str, None]:
        """
        Interrupt the current run and redirect the agent.

        1. Cancel active stream (if any) and wait for state persistence
        2. Load persisted state (includes partial assistant output)
        3. If deferred approvals exist, auto-deny them
        4. Append steering user message
        5. Start new agent run
        """
        from suzent.core.run_state import cancel_and_wait

        # 1. Cancel and wait for cleanup
        await cancel_and_wait(chat_id)

        # 2. Load persisted state from DB
        message_history = None
        try:
            db = get_database()
            chat = db.get_chat(chat_id)
            if chat and chat.agent_state:
                from suzent.core.agent_serializer import deserialize_state

                state = deserialize_state(chat.agent_state)
                if state and state.get("message_history"):
                    message_history = state["message_history"]
        except Exception as e:
            logger.error(f"Error restoring history for steer: {e}")

        if message_history is None:
            message_history = []

        # 3. Auto-deny any pending deferred tool approvals
        from pydantic_ai.messages import (
            ModelResponse,
            ModelRequest,
            ToolCallPart,
            ToolReturnPart,
        )

        if message_history:
            last_msg = message_history[-1]
            if isinstance(last_msg, ModelResponse):
                # Check for unanswered tool calls — add denial returns
                answered_ids = set()
                for msg in message_history:
                    if isinstance(msg, ModelRequest):
                        for part in msg.parts:
                            if isinstance(part, ToolReturnPart):
                                answered_ids.add(part.tool_call_id)

                unanswered_calls = []
                for part in last_msg.parts:
                    if (
                        isinstance(part, ToolCallPart)
                        and part.tool_call_id not in answered_ids
                    ):
                        unanswered_calls.append(part)

                if unanswered_calls:
                    denial_parts = [
                        ToolReturnPart(
                            tool_name=tc.tool_name,
                            tool_call_id=tc.tool_call_id,
                            content="Cancelled: user redirected the conversation",
                        )
                        for tc in unanswered_calls
                    ]
                    message_history.append(ModelRequest(parts=denial_parts))

        # 4. Append steering message
        from pydantic_ai.messages import UserPromptPart

        steering_text = f"[User interrupted to redirect]: {steer_message}"
        message_history.append(
            ModelRequest(parts=[UserPromptPart(content=steering_text)])
        )

        # 5. Start new agent run via process_turn with pre-built history
        async for chunk in self.process_turn(
            chat_id=chat_id,
            user_id=user_id,
            message_content="",
            config_override=config_override,
            _message_history_override=message_history,
        ):
            yield chunk

    async def process_steer_text(
        self,
        chat_id: str,
        user_id: str,
        steer_message: str,
        config_override: Dict = None,
        on_event: Any = None,
        _stream_queue=None,
    ) -> str:
        """Run a steer and return only the final response text.

        If `_stream_queue` is an asyncio.Queue, each raw SSE chunk is also put
        on that queue so live subscribers can receive events in real time.
        A None sentinel is put at the end to signal completion.
        """
        full_response = ""
        parser = StreamParser()

        async for chunk in self.process_steer(
            chat_id=chat_id,
            user_id=user_id,
            steer_message=steer_message,
            config_override=config_override,
        ):
            if _stream_queue is not None:
                await _stream_queue.put(chunk)
            for event in parser.parse([chunk]):
                if on_event:
                    await on_event(event)
                if isinstance(event, TextChunk):
                    full_response += event.content
                elif isinstance(event, ErrorEvent):
                    raise RuntimeError(event.message)

        if _stream_queue is not None:
            await _stream_queue.put(None)  # sentinel: stream finished

        return full_response.strip()

    async def process_turn_text(
        self,
        chat_id: str,
        user_id: str,
        message_content: str,
        files: List[Any] = None,
        config_override: Dict = None,
        on_event: Any = None,
        resume_approvals: List[Dict] = None,
        is_social: bool = False,
        is_heartbeat: bool = False,
        _stream_queue=None,
    ) -> str:
        """Run a conversation turn and return only the final response text.

        Allows for an optional async 'on_event' callback to handle intermediate
        events (like tool approval requests) while draining the stream.

        If `_stream_queue` is an asyncio.Queue, each raw SSE chunk is also put
        on that queue so live subscribers can receive events in real time.
        A None sentinel is put at the end to signal completion.
        """
        full_response = ""
        parser = StreamParser()

        async for chunk in self.process_turn(
            chat_id=chat_id,
            user_id=user_id,
            message_content=message_content,
            files=files,
            config_override=config_override,
            resume_approvals=resume_approvals,
            is_social=is_social,
            is_heartbeat=is_heartbeat,
        ):
            if _stream_queue is not None:
                await _stream_queue.put(chunk)

            # Use the shared parser to turn raw SSE chunks into events
            for event in parser.parse([chunk]):
                if on_event:
                    await on_event(event)

                if isinstance(event, TextChunk):
                    full_response += event.content
                elif isinstance(event, ErrorEvent):
                    raise RuntimeError(event.message)

        if _stream_queue is not None:
            await _stream_queue.put(None)  # sentinel: stream finished

        return full_response.strip()

    async def _process_upload_file(
        self, file_obj, host_path: Path, virtual_path_prefix: str
    ) -> Dict:
        """Handle Starlette UploadFile."""
        filename = getattr(file_obj, "filename", "unnamed")
        content_type = getattr(file_obj, "content_type", "")

        safe_name = sanitize_filename(filename)
        target_path = _resolve_target_path(host_path, safe_name)

        content = await file_obj.read()
        with open(target_path, "wb") as f:
            f.write(content)

        virtual_path = f"{virtual_path_prefix}/{target_path.name}"
        logger.info(f"Saved uploaded file to {virtual_path}")

        return {
            "final_path": str(target_path),
            "virtual_path": virtual_path,
            "filename": filename,
            "is_image": content_type.startswith("image/"),
        }

    def _process_social_attachment(
        self, att_dict: Dict, host_path: Path, virtual_path_prefix: str
    ) -> Dict:
        """Handle social attachment dict."""
        src_path = att_dict.get("path")
        filename = att_dict.get("filename", "unnamed")
        att_type = att_dict.get("type")

        if not src_path or not os.path.exists(src_path):
            return {"final_path": None, "virtual_path": None, "is_image": False}

        safe_name = sanitize_filename(filename)
        target_path = _resolve_target_path(host_path, safe_name)

        shutil.move(src_path, target_path)

        virtual_path = f"{virtual_path_prefix}/{target_path.name}"
        return {
            "final_path": str(target_path),
            "virtual_path": virtual_path,
            "filename": filename,
            "is_image": att_type == "image",
        }

    async def _extract_memories(
        self, chat_id, user_id, user_content, agent_content, messages
    ):
        """Extract memories from pydantic-ai message history."""
        if not CONFIG.memory_enabled:
            return

        try:
            memory_mgr = get_memory_manager()
            if not memory_mgr:
                return

            # Extract tool calls from messages
            actions = _extract_tool_calls(messages)

            conversation_turn = ConversationTurn(
                user_message=Message(role="user", content=user_content),
                assistant_message=Message(role="assistant", content=agent_content),
                agent_actions=actions,
            )

            await memory_mgr.process_conversation_turn_for_memories(
                conversation_turn=conversation_turn,
                chat_id=chat_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.error(f"Memory extraction failed for {chat_id}: {e}")

    async def _write_transcript(
        self, chat_id: str, user_content: str, agent_content: str, messages: list
    ) -> None:
        """Write user and assistant turns to the JSONL transcript."""
        try:
            from suzent.session.transcript import TranscriptManager

            tm = TranscriptManager()
            await tm.append_turn(chat_id, "user", user_content)

            actions = []
            for action in _extract_tool_calls(messages):
                actions.append({"tool": action.tool, "args": action.args})

            await tm.append_turn(
                chat_id, "assistant", agent_content, actions=actions or None
            )

        except Exception as e:
            logger.debug(f"Transcript write failed for {chat_id}: {e}")

    async def _persist_state(
        self,
        chat_id: str,
        messages: list,
        model_id: Optional[str],
        tool_names: List[str],
        user_content: str,
        agent_content: str,
        skip_messages: bool = False,
    ) -> None:
        """Persist conversation state to database."""
        try:
            from datetime import datetime

            db = get_database()
            agent_state = serialize_state(
                messages, model_id=model_id, tool_names=tool_names
            )

            current_chat = db.get_chat(chat_id)
            chat_messages = current_chat.messages if current_chat else []
            prev_turn_count = getattr(current_chat, "turn_count", 0) or 0

            if skip_messages:
                # Heartbeat: rollback already owns message state; only save agent_state.
                db.update_chat(chat_id, agent_state=agent_state)
            else:
                # 100% Backend Authored: rebuild the complete display log from the full agent history
                # so chat.messages is always a faithful log of all exchanges, including tools and reasoning.
                rebuilt = _rebuild_display_messages(messages)
                db.update_chat(
                    chat_id, agent_state=agent_state, messages=rebuilt or chat_messages
                )

            # Update session lifecycle fields
            try:
                from sqlalchemy import text as sql_text

                with db._session() as session:
                    session.exec(
                        sql_text(
                            "UPDATE chats SET last_active_at = :ts, turn_count = :tc WHERE id = :cid"
                        ),
                        params={
                            "ts": datetime.now().isoformat(),
                            "tc": prev_turn_count + 1,
                            "cid": chat_id,
                        },
                    )
                    session.commit()
            except Exception as lc_err:
                logger.debug(f"Lifecycle field update failed: {lc_err}")

            # Mirror state to inspectable JSON file
            if agent_state:
                try:
                    from suzent.session.state_mirror import StateMirror

                    StateMirror().mirror_state(chat_id, agent_state)
                except Exception as mirror_err:
                    logger.debug(f"State mirror failed: {mirror_err}")

            logger.info(f"Persisted state for chat {chat_id}")

        except Exception as e:
            logger.error(f"Failed to persist state for {chat_id}: {e}")


# ─── Utility ───────────────────────────────────────────────────────────


def _extract_tool_calls(messages: list) -> List[AgentAction]:
    """Extract AgentAction records from pydantic-ai message history."""
    from pydantic_ai.messages import (
        ModelResponse,
        ModelRequest,
        ToolCallPart,
        ToolReturnPart,
    )

    actions = []
    # Build a map of tool_call_id → return content
    returns: Dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    returns[part.tool_call_id] = str(part.content)[:200]

    # Extract tool calls
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    output = returns.get(part.tool_call_id, "")
                    actions.append(
                        AgentAction(
                            tool=part.tool_name,
                            args=part.args if isinstance(part.args, dict) else {},
                            output=output,
                        )
                    )

    return actions


def _rebuild_display_messages(messages: list) -> list:
    """
    Reconstruct an OpenAI-like JSON display log from pydantic-ai message history.
    This ensures that tool calls and tool results are preserved in the database.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        UserPromptPart,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
    )
    import json

    # First pass: find all tool calls that have a corresponding return
    executed_tool_calls = set()
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    executed_tool_calls.add(part.tool_call_id)

    result = []
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    content = (
                        part.content
                        if isinstance(part.content, str)
                        else str(part.content)
                    )
                    ts = (
                        part.timestamp.isoformat()
                        if getattr(part, "timestamp", None)
                        else None
                    )
                    entry: dict = {"role": "user", "content": content}
                    if ts:
                        entry["timestamp"] = ts
                    result.append(entry)
                elif isinstance(part, ToolReturnPart):
                    ts = (
                        part.timestamp.isoformat()
                        if getattr(part, "timestamp", None)
                        else None
                    )
                    entry = {
                        "role": "tool",
                        "tool_call_id": part.tool_call_id,
                        "name": part.tool_name,
                        "content": str(part.content),
                    }
                    if ts:
                        entry["timestamp"] = ts
                    result.append(entry)
        elif isinstance(msg, ModelResponse):
            text_parts = []
            tool_calls = []
            for part in msg.parts:
                if isinstance(part, TextPart):
                    text_parts.append(part.content)
                elif isinstance(part, ToolCallPart):
                    args_str = (
                        json.dumps(part.args)
                        if isinstance(part.args, dict)
                        else str(part.args)
                    )
                    tc_dict = {
                        "id": part.tool_call_id,
                        "type": "function",
                        "function": {"name": part.tool_name, "arguments": args_str},
                    }
                    if part.tool_call_id not in executed_tool_calls:
                        tc_dict["state"] = "approval-requested"
                    tool_calls.append(tc_dict)

            text_content = "".join(text_parts) if text_parts else None
            # Only skip if there's no text AND no tool calls
            if not text_content and not tool_calls:
                continue

            ts = msg.timestamp.isoformat() if getattr(msg, "timestamp", None) else None
            entry = {"role": "assistant", "content": text_content}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if ts:
                entry["timestamp"] = ts
            result.append(entry)
    return result
