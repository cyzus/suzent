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
from typing import AsyncGenerator, List, Dict, Any

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

        # 4. Restore message history from DB
        message_history = None
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

        # 6. Prepare Prompt
        full_prompt = message_content + attachment_context

        from pydantic_ai.messages import ModelRequest, UserPromptPart

        parts = [UserPromptPart(content=full_prompt)]
        if agent_images:
            parts.extend(agent_images)

        new_request = ModelRequest(parts=parts)

        if message_history is None:
            message_history = []
        message_history.append(new_request)

        logger.debug(
            f"[ChatProcessor] Prompt prepared. Length: {len(full_prompt)}. Streaming..."
        )

        # 7. Stream Response
        full_response = ""

        async for chunk in stream_agent_responses(
            agent,
            None,
            deps=deps,
            message_history=message_history,
            chat_id=chat_id,
        ):
            try:
                if chunk.startswith("data: "):
                    json_str = chunk[6:].strip()
                    if json_str == "[DONE]":
                        continue
                    event_data = json.loads(json_str)

                    msg_type = event_data.get("type")
                    if msg_type == "text-delta":
                        full_response += event_data.get("delta", "")
            except Exception:
                pass

            yield chunk

        # 8. Post-Processing

        # Get the messages from the agent or deps for persistence
        last_messages = getattr(deps, "last_messages", None)
        if last_messages is None:
            last_messages = getattr(agent, "_last_messages", [])

        # A. Write JSONL transcript
        await self._write_transcript(
            chat_id, message_content, full_response, last_messages
        )

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
        compressed_messages = await compressor.compress_messages(last_messages)

        # D. State Persistence
        await self._persist_state(
            chat_id=chat_id,
            messages=compressed_messages,
            model_id=getattr(agent, "_model_id", None),
            tool_names=getattr(agent, "_tool_names", []),
            user_content=message_content,
            agent_content=full_response,
        )

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

    async def _write_transcript(self, chat_id, user_content, agent_content, messages):
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
        self, chat_id, messages, model_id, tool_names, user_content, agent_content
    ):
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

            chat_messages.append({"role": "user", "content": user_content})
            chat_messages.append({"role": "assistant", "content": agent_content})

            db.update_chat(chat_id, agent_state=agent_state, messages=chat_messages)

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
