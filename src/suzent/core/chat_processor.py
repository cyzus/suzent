"""
Chat Processor: Unified logic for handling conversation turns.
"""

import os
import shutil
import json
import time
from pathlib import Path
from typing import AsyncGenerator, List, Dict, Any
from PIL import Image

from suzent.logger import get_logger
from suzent.config import CONFIG, get_effective_volumes
from suzent.agent_manager import get_or_create_agent, deserialize_agent

from suzent.core.context_injection import inject_chat_context
from suzent.core.agent_serializer import serialize_agent
from suzent.core.context_compressor import ContextCompressor
from suzent.memory.lifecycle import get_memory_manager
from suzent.streaming import stream_agent_responses
from suzent.memory import AgentStepsSummary, ConversationTurn, Message
from suzent.database import get_database
from suzent.tools.path_resolver import PathResolver
from suzent.routes.sandbox_routes import sanitize_filename

logger = get_logger(__name__)


def _resolve_target_path(host_path: Path, filename: str) -> Path:
    """
    Resolve a safe target path, appending a timestamp suffix on collision.

    Args:
        host_path: Directory to place the file in.
        filename: Original filename (already sanitized).

    Returns:
        Path that does not collide with existing files.
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
        files: List[Any] = None,  # List of UploadFile or dict (social)
        config_override: Dict = None,
        is_social: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Process a user message turn:
        1. Context & Agent Setup
        2. Attachment Processing
        3. Response Streaming
        4. Background Tasks (Memory, Compression, Persistence)
        """

        # 1. Configuration
        config = {
            "_user_id": user_id,
            "_chat_id": chat_id,
            "memory_enabled": CONFIG.memory_enabled,
        }
        if config_override:
            config.update(config_override)

        # 2. Get Agent (Default/Global)
        agent = await get_or_create_agent(config)

        # 2b. Restore State from DB (if exists)
        # This ensures we continue the specific conversation state
        try:
            db = get_database()
            chat = db.get_chat(chat_id)
            if chat and chat.agent_state:
                logger.debug(f"Attempting to restore agent state for chat {chat_id}")
                restored_agent = deserialize_agent(chat.agent_state, config)
                if restored_agent:
                    logger.debug(f"Restored agent state for {chat_id}")
                    agent = restored_agent
                else:
                    logger.warning(f"Failed to deserialize agent state for {chat_id}")
        except Exception as e:
            logger.error(f"Error restoring agent state: {e}")

        # 3. Context Injection (Tools, Memory)
        inject_chat_context(agent, chat_id, user_id, config)

        # 4. Attachment Handling (Async)
        agent_images = []
        attachment_context = ""

        # We need a unified way to handle files (UploadFile vs Social Dict)
        # Assuming `files` contains objects we can process or dicts

        if files:
            # We need to setup sandbox path resolver here to move files
            try:
                # Basic sandbox setup
                custom_volumes = get_effective_volumes([])
                resolver = PathResolver(
                    chat_id=chat_id,
                    sandbox_enabled=True,  # Always enable sandbox storage for persistence
                    custom_volumes=custom_volumes,
                )

                # Resolve persistence path
                uploads_virtual_path = "/persistence/uploads"
                uploads_host_path = resolver.resolve(uploads_virtual_path)
                uploads_host_path.mkdir(parents=True, exist_ok=True)

                # Process files
                for file_item in files:
                    # Handle difference between Starlette UploadFile and Social Dict
                    if isinstance(file_item, dict):
                        # Social context format
                        result = self._process_social_attachment(
                            file_item, uploads_host_path, uploads_virtual_path
                        )
                    else:
                        # UploadFile format (Starlette)
                        result = await self._process_upload_file(
                            file_item, uploads_host_path, uploads_virtual_path
                        )

                    if result["is_image"]:
                        try:
                            # Load image for agent
                            img = Image.open(result["final_path"])
                            agent_images.append(img)
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

        # 5. Prepare Prompt
        full_prompt = message_content + attachment_context

        # 6. Stream Response
        full_response = ""

        async for chunk in stream_agent_responses(
            agent, full_prompt, chat_id=chat_id, images=agent_images
        ):
            # Capture content for full_response
            # The chunks are SSE formatted strings "data: ..."
            # We parse them to extract the text content for our internal use
            # But we YIELD the raw chunk to the caller so they can forward it

            try:
                if chunk.startswith("data: "):
                    json_str = chunk[6:].strip()
                    data = json.loads(json_str)
                    if data.get("type") == "final_answer":
                        # This contains the accumulative final answer
                        full_response = data.get("data", "")
            except Exception:
                pass

            yield chunk

        # 7. Post-Processing (Background Tasks)
        # We execute these serially here but they could be truly async tasks
        # However, for consistency we typically await them currently.

        # A. Memory Extraction
        await self._extract_memories(
            chat_id=chat_id,
            user_id=user_id,
            user_content=message_content,
            agent_content=full_response,
            agent=agent,
        )

        # B. Context Compression
        # If compressed, the agent state in memory is updated
        compressor = ContextCompressor()
        await compressor.compress_context(agent)

        # C. State Persistence
        # Save state + History
        await self._persist_state(
            chat_id=chat_id,
            agent=agent,
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
        self, chat_id, user_id, user_content, agent_content, agent
    ):
        if not CONFIG.memory_enabled:
            return

        try:
            memory_mgr = get_memory_manager()
            if not memory_mgr:
                return

            # Extract steps
            if hasattr(agent.memory, "get_succinct_steps"):
                succinct_steps = agent.memory.get_succinct_steps()
                steps = AgentStepsSummary.from_succinct_steps(succinct_steps)
            else:
                # Fallback if method missing (should exist in our custom agent)
                steps = AgentStepsSummary(actions=[], planning=[])

            conversation_turn = ConversationTurn(
                user_message=Message(role="user", content=user_content),
                assistant_message=Message(role="assistant", content=agent_content),
                agent_actions=steps.actions,
                agent_reasoning=steps.planning,
            )

            await memory_mgr.process_conversation_turn_for_memories(
                conversation_turn=conversation_turn,
                chat_id=chat_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.error(f"Memory extraction failed for {chat_id}: {e}")

    async def _persist_state(self, chat_id, agent, user_content, agent_content):
        try:
            db = get_database()
            agent_state = serialize_agent(agent)

            # Simple history update
            # (Note: In a real app we might not want to fetch the whole chat just to append,
            # but our DB interface is simple currently)
            current_chat = db.get_chat(chat_id)
            messages = current_chat.messages if current_chat else []

            messages.append({"role": "user", "content": user_content})
            messages.append({"role": "assistant", "content": agent_content})

            db.update_chat(chat_id, agent_state=agent_state, messages=messages)
            logger.info(f"Persisted state for chat {chat_id}")

        except Exception as e:
            logger.error(f"Failed to persist state for {chat_id}: {e}")
