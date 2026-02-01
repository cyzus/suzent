"""
Social Brain: The bridge between Social Channels and the Suzent Agent.
"""

import asyncio
from typing import Optional, List
from PIL import Image
from suzent.logger import get_logger
from suzent.channels.manager import ChannelManager
from suzent.channels.base import UnifiedMessage
from suzent.agent_manager import get_or_create_agent, inject_chat_context, get_memory_manager, serialize_agent
from suzent.streaming import stream_agent_responses
from suzent.memory import AgentStepsSummary, ConversationTurn, Message
from suzent.config import CONFIG, get_effective_volumes
from suzent.database import get_database
from suzent.tools.path_resolver import PathResolver
from suzent.routes.sandbox_routes import sanitize_filename
import shutil
import os

logger = get_logger(__name__)

class SocialBrain:
    """
    Consumer that processes messages from the ChannelManager queue 
    and dispatches them to the AI Agent.
    """

    def __init__(self, channel_manager: ChannelManager, allowed_users: list = None, platform_allowlists: dict = None):
        self.channel_manager = channel_manager
        self.allowed_users = set(allowed_users) if allowed_users else set()
        self.platform_allowlists = {k: set(v) for k, v in platform_allowlists.items()} if platform_allowlists else {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the processing loop."""
        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("SocialBrain started.")

    async def stop(self):
        """Stop the processing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SocialBrain stopped.")

    async def _process_queue(self):
        """Main loop consuming messages."""
        while self._running:
            try:
                # Wait for message
                message: UnifiedMessage = await self.channel_manager.message_queue.get()
                
                # Process in background task to not block queue
                asyncio.create_task(self._handle_message(message))
                
                self.channel_manager.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SocialBrain loop: {e}")
                await asyncio.sleep(1)

    def _is_authorized(self, message: UnifiedMessage) -> bool:
        """Check if a message sender is authorized."""
        # No restrictions if both lists are empty
        platform_allowed = self.platform_allowlists.get(message.platform)
        if not self.allowed_users and not platform_allowed:
            return True

        # Check if sender is in either global or platform-specific allowlist
        identifiers = {message.sender_id, message.sender_name}

        if self.allowed_users and identifiers & self.allowed_users:
            return True

        if platform_allowed and identifiers & platform_allowed:
            return True

        return False

    async def _handle_message(self, message: UnifiedMessage):
        """
        Handle a single message:
        1. Access Control Check.
        2. Resolve/Create Suzent Chat ID.
        3. Invoke Agent.
        4. Send Response.
        """
        # 1. Access Control
        if not self._is_authorized(message):
            logger.warning(f"Unauthorized social message from: {message.sender_name} ({message.sender_id}) on {message.platform}")
            await self.channel_manager.send_message(
                message.platform, 
                message.sender_id, 
                "⛔ Access Denied. You are not authorized to use this bot."
            )
            return

        try:
            # 2. Resolve Chat ID
            # We use a stable mapping: platform:sender_id -> Chat ID
            # Ideally stored in DB, but for now we can use a deterministic ID or lookup
            # Let's check if we have a chat for this "external_id"
            # Since standard chats are UUIDs, maybe we create a specialized chat?
            # Or we just use a hash/string as ID? Agent Manager expects string.
            
            # Simple approach: "social-{platform}-{sender_id}"
            social_chat_id = f"social-{message.platform}-{message.sender_id}"
            
            # Ensure chat exists in DB (to store history/state)
            self._ensure_chat_exists(social_chat_id, message)
            
            # 2. Invoke Agent
            logger.info(f"Processing social message for {social_chat_id}: {message.content}")
            
            # Indicate typing?
            # await self.channel_manager.send_chat_action(message.platform, message.sender_id, "typing")

            # Config for agent
            config = {
                "_user_id": CONFIG.user_id, # Default user
                "_chat_id": social_chat_id,
                "memory_enabled": True # Enable memory for social too
            }
            
            # Get Agent
            agent = await get_or_create_agent(config)
            
            # Inject context
            inject_chat_context(agent, social_chat_id, CONFIG.user_id, config)
            
            # Run Agent and Aggregate Response
            full_response = ""
            
            # Stream generator
            
            # Process Attachments (Generalization)
            agent_images = []
            attachment_context = ""
            
            # Setup Sandbox Storage
            # We want to move these files to /persistence/uploads so the agent can access them via tools
            try:
                # Same logic as sandbox_routes to get resolver
                # Note: We rely on default volumes for now as we don't have request state
                custom_volumes = get_effective_volumes([]) 
                resolver = PathResolver(chat_id=social_chat_id, sandbox_enabled=True, custom_volumes=custom_volumes)
                
                # Resolve host path
                uploads_virtual_path = "/persistence/uploads"
                uploads_host_path = resolver.resolve(uploads_virtual_path)
                uploads_host_path.mkdir(parents=True, exist_ok=True)
                
            except Exception as e:
                logger.error(f"Failed to setup sandbox storage for social: {e}")
                uploads_host_path = None

            if message.attachments:
                for att in message.attachments:
                    result = self._process_attachment(att, uploads_host_path, uploads_virtual_path)
                    
                    if result["is_image"]:
                        try:
                            img = Image.open(result["final_path"])
                            agent_images.append(img)
                            attachment_context += f"\n[User attached an image: {result['virtual_path']}]"
                        except Exception as img_err:
                            logger.error(f"Failed to load image for agent: {img_err}")
                            attachment_context += f"\n[Failed to load attached image: {att.get('filename')}]"
                    elif result["virtual_path"]:
                         attachment_context += f"\n[User attached a file: {result['virtual_path']}]"


            # Augment message with attachment context
            full_prompt = message.content + attachment_context
            
            logger.debug(f"Streaming agent response for social... (Images: {len(agent_images)})")
            
            async for chunk in stream_agent_responses(
                agent,
                full_prompt,
                chat_id=social_chat_id,
                images=agent_images
            ):
                # Chunk format is SSE string: "data: {json}\n\n"
                # We need to parse it
                if chunk.startswith("data: "):
                    import json
                    try:
                        json_str = chunk[6:].strip()
                        data = json.loads(json_str)
                        event_type = data.get("type")
                        content = data.get("data")
                        
                        if event_type == "final_answer":
                            # Accumulate text (final answer step contains full text usually)
                            # Or should we use stream_delta?
                            # FinalAnswerStep logic in streaming.py:
                            # event_type == "final_answer" -> data = output.to_string()
                            # So it is the full string.
                            full_response = content # Replace, don't append, as it's the final answer
                        elif event_type == "stream_delta":
                             # Optional: we could accumulate deltas if final_answer is missing?
                             # But usually final_answer comes at the end.
                             # For now, let's rely on final_answer.
                             pass
                        elif event_type == "error":
                            logger.error(f"Agent error: {content}")
                            await self.channel_manager.send_message(
                                message.platform, 
                                message.sender_id, 
                                f"⚠️ Error: {content}"
                            )
                            return
                            
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse chunk: {json_str} - {parse_err}")

            # 3. Send Final Response
            if full_response.strip():
                await self.channel_manager.send_message(
                    message.platform,
                    message.sender_id,
                    full_response
                )
                
                # 4. Background Memory Extraction (Fire and Forget)
                try:
                    memory_mgr = get_memory_manager()
                    if memory_mgr:
                        # Extract steps for summary
                        succinct_steps = agent.memory.get_succinct_steps()
                        steps = AgentStepsSummary.from_succinct_steps(succinct_steps)
                        
                        conversation_turn = ConversationTurn(
                            user_message=Message(role="user", content=message.content),
                            assistant_message=Message(role="assistant", content=full_response),
                            agent_actions=steps.actions,
                            agent_reasoning=steps.planning,
                        )
                        
                        logger.info(f"Extracting memories for social chat {social_chat_id}")
                        await memory_mgr.process_conversation_turn_for_memories(
                            conversation_turn=conversation_turn,
                            chat_id=social_chat_id,
                            user_id=CONFIG.user_id,
                        )
                except Exception as mem_err:
                    logger.error(f"Failed to extract social memories: {mem_err}")

            # 5. Persist Agent State AND Message History
            try:
                db = get_database()
                agent_state = serialize_agent(agent)
                
                # Retrieve current chat to get simple history list
                # (Ideally we'd have a better history management than just a JSON blob)
                current_chat = db.get_chat(social_chat_id)
                messages = current_chat.messages if current_chat and current_chat.messages else []
                
                # Append User Message
                messages.append({
                    "role": "user",
                    "content": message.content,
                    # Add attachments context to hidden/system prompt if needed, 
                    # but for history display we just show content + maybe "Attachments: ..."
                    # The frontend likely just shows 'content'.
                })
                
                # Append Assistant Message
                messages.append({
                    "role": "assistant",
                    "content": full_response
                })
                
                db.update_chat(social_chat_id, agent_state=agent_state, messages=messages)
                logger.info("Persisted social chat history and state.")
                
            except Exception as e:
                logger.error(f"Error saving social agent state/history: {e}")

        except Exception as e:
            logger.error(f"Failed to handle social message: {e}")
    def _process_attachment(self, att: dict, uploads_host_path: Optional[object], uploads_virtual_path: str) -> dict:
        """
        Process a single attachment: move to sandbox if possible, return metadata.
        """
        att_type = att.get("type")
        att_path = att.get("path")
        att_name = att.get("filename") or "unnamed_file"
        
        result = {
            "final_path": att_path,
            "virtual_path": att_path,
            "is_image": att_type == "image"
        }

        if att_path and os.path.exists(att_path):
            # Move to Sandbox
            if uploads_host_path:
                try:
                    safe_name = sanitize_filename(att_name)
                    target_file = uploads_host_path / safe_name
                    
                    # Handle collisions
                    if target_file.exists():
                        stem = target_file.stem
                        suffix = target_file.suffix
                        import time
                        timestamp = int(time.time() * 1000)
                        target_file = uploads_host_path / f"{stem}_{timestamp}{suffix}"
                    
                    shutil.move(att_path, target_file)
                    result["final_path"] = str(target_file)
                    result["virtual_path"] = f"{uploads_virtual_path}/{target_file.name}"
                    logger.info(f"Moved social attachment to sandbox: {result['virtual_path']}")
                    
                except Exception as move_err:
                    logger.error(f"Failed to move attachment to sandbox: {move_err}")
            
            # Update message attachment
            att["path"] = result["final_path"]
            att["virtual_path"] = result["virtual_path"]

        return result


    def _ensure_chat_exists(self, chat_id: str, message: UnifiedMessage):
        """Ensure a record exists in the DB for this chat."""
        db = get_database()
        chat = db.get_chat(chat_id)
        if not chat:
            title = f"Chat with {message.sender_name} ({message.platform})"
            logger.info(f"Creating new social chat: {title} ({chat_id})")
            db.create_chat(
                title=title,
                config={"platform": message.platform, "sender_id": message.sender_id},
                chat_id=chat_id
            )
