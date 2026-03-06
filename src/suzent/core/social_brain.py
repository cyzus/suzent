"""
Social Brain: The bridge between Social Channels and the Suzent Agent.
"""

import asyncio
from typing import Optional, Dict
from suzent.logger import get_logger
from suzent.channels.manager import ChannelManager
from suzent.channels.base import UnifiedMessage
from suzent.config import CONFIG
from suzent.core.base_brain import BaseBrain, get_active
from suzent.core.approval_manager import PendingApprovalSession
from suzent.core.stream_parser import ApprovalRequest
from suzent.database import get_database

logger = get_logger(__name__)


def get_active_social_brain() -> Optional["SocialBrain"]:
    """Return the active SocialBrain instance, or None if not running."""
    return get_active(SocialBrain)


class SocialBrain(BaseBrain):
    """
    Consumer that processes messages from the ChannelManager queue
    and dispatches them to the AI Agent.
    """

    _brain_name = "SocialBrain"

    def __init__(
        self,
        channel_manager: ChannelManager,
        allowed_users: list = None,
        platform_allowlists: dict = None,
        model: str = None,
        memory_enabled: bool = True,
        tools: list = None,
        mcp_enabled: dict = None,
    ):
        super().__init__()
        self.channel_manager = channel_manager
        self.allowed_users = set(allowed_users) if allowed_users else set()
        self.platform_allowlists = (
            {k: set(v) for k, v in platform_allowlists.items()}
            if platform_allowlists
            else {}
        )
        self.model = model
        self.memory_enabled = memory_enabled
        self.tools = tools
        self.mcp_enabled = mcp_enabled
        self._sessions: Dict[str, PendingApprovalSession] = {}  # chat_id -> session
        self._session_policies: Dict[
            str, Dict[str, str]
        ] = {}  # chat_id -> {tool -> policy}

    def update_model(self, model: str):
        """Update the model used for social interactions."""
        self.model = model

    async def start(self):
        """Start the processing loop."""
        await super().start()

    async def _run_loop(self):
        """Delegate to the queue processor."""
        await self._process_queue()

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
        Handle a single message using ChatProcessor.
        """
        # 1. Access Control
        if not self._is_authorized(message):
            logger.warning(
                f"Unauthorized social message from: {message.sender_name} ({message.sender_id}) on {message.platform}"
            )
            await self.channel_manager.send_message(
                message.platform,
                message.sender_id,
                "⛔ Access Denied. You are not authorized to use this bot.",
            )
            return

        # 1.5 Slash command interception
        from suzent.social.commands import dispatch_command

        if await dispatch_command(message, self.channel_manager):
            return

        try:
            # 2. Resolve Chat ID and target
            # target_id is thread/group ID when available, sender_id for DMs
            from suzent.channels.utils import extract_target_id

            target_id = extract_target_id(message)
            social_chat_id = f"social-{message.platform}-{target_id}"
            self._ensure_chat_exists(social_chat_id, message, target_id)

            logger.info(
                f"Processing social message for {social_chat_id}: {message.content}"
            )

            # 3. Envelope header — prepend platform metadata to message
            envelope = f"[{message.platform.title()} {message.sender_name} id:{message.sender_id}]"
            enriched_content = f"{envelope}\n{message.content}"

            # 4. Setup Processor
            from suzent.core.chat_processor import ChatProcessor

            processor = ChatProcessor()

            # Capture the running event loop for sync-to-async bridging in tools
            event_loop = asyncio.get_running_loop()

            # Prepare config overrides with social context and runtime refs
            from suzent.agent_manager import build_agent_config

            base_config = {
                "mcp_enabled": self.mcp_enabled,
                "social_context": {
                    "platform": message.platform,
                    "sender_name": message.sender_name,
                    "sender_id": message.sender_id,
                    "target_id": target_id,
                },
                "_runtime": {
                    "channel_manager": self.channel_manager,
                    "event_loop": event_loop,
                },
            }
            if self.model:
                base_config["model"] = self.model
            if self.tools is not None:
                base_config["tools"] = self.tools

            config_override = build_agent_config(base_config, require_social_tool=False)

            # Inject any session-level tool approval policies
            policies = self._session_policies.get(social_chat_id)
            if policies:
                config_override["tool_approval_policy"] = dict(policies)

            # 5. Process and Reply — collect all approval requests from the stream
            collected_approvals: list[ApprovalRequest] = []

            async def on_event(event):
                if isinstance(event, ApprovalRequest):
                    logger.info(
                        f"SocialBrain: Collected approval request for {event.tool_name}"
                    )
                    collected_approvals.append(event)

            full_response = await processor.process_turn_text(
                chat_id=social_chat_id,
                user_id=CONFIG.user_id,
                message_content=enriched_content,
                files=message.attachments,
                config_override=config_override,
                on_event=on_event,
            )

            # If tools need approval, store the session and prompt the first one
            if collected_approvals:
                session = PendingApprovalSession(
                    requests=collected_approvals,
                    config_override=config_override,
                    platform=message.platform,
                    target_id=target_id,
                    sender_id=message.sender_id,
                )
                self._sessions[social_chat_id] = session
                await self._prompt_next_approval(session)

            # Send Final Response
            if full_response.strip():
                await self.channel_manager.send_message(
                    message.platform, target_id, full_response
                )

        except Exception as e:
            logger.error(f"Failed to handle social message: {e}")

    async def _prompt_next_approval(self, session: PendingApprovalSession):
        """Send the next approval prompt to the social channel."""
        req = session.next_request
        if not req:
            return

        counter = (
            f"({session.current_index + 1}/{session.total}) "
            if session.total > 1
            else ""
        )
        alert = (
            f"⚠️ Approval Required {counter}\n"
            f"{req.format_alert_text(markdown=False)}\n\n"
            f"/y allow | /n deny | /ya always allow | /na always deny"
        )
        await self.channel_manager.send_message(
            session.platform, session.target_id, alert
        )

    async def handle_approval_response(
        self,
        platform: str,
        target_id: str,
        approved: bool,
        sender_id: str = "",
        remember: bool = False,
    ):
        """Record a user's /y or /n and either prompt the next tool or resume the agent."""
        social_chat_id = f"social-{platform}-{target_id}"
        session = self._sessions.get(social_chat_id)

        if not session or session.all_decided:
            await self.channel_manager.send_message(
                platform, target_id, "No pending tool approval found for this chat."
            )
            return

        # In group chats, only the original requester may approve
        if session.sender_id and sender_id and session.sender_id != sender_id:
            await self.channel_manager.send_message(
                platform,
                target_id,
                "Only the original requester can approve or deny this tool call.",
            )
            return

        # Record this decision
        req = session.next_request
        session.record(approved)

        # Confirmation message
        tool_name = req.tool_name if req else "tool"
        status = "Approved" if approved else "Denied"
        suffix = " (remembered for session)" if remember else ""
        await self.channel_manager.send_message(
            platform, target_id, f"{status} {tool_name}{suffix}"
        )

        # Persist "always" policy for this session
        if remember and req:
            policy = "always_allow" if approved else "always_deny"
            self._session_policies.setdefault(social_chat_id, {})[req.tool_name] = (
                policy
            )

        logger.info(
            f"SocialBrain: Decision {session.current_index}/{session.total} "
            f"for {social_chat_id}: approved={approved} remember={remember}"
        )

        # More approvals to collect? Prompt the next one.
        if not session.all_decided:
            await self._prompt_next_approval(session)
            return

        # All decided — resume the agent with batched decisions
        session = self._sessions.pop(social_chat_id)
        await self._resume_after_approval(social_chat_id, session)

    async def _resume_after_approval(
        self, social_chat_id: str, session: PendingApprovalSession
    ):
        """Resume the agent turn after all approvals are collected."""
        try:
            from suzent.core.chat_processor import ChatProcessor

            processor = ChatProcessor()

            # Ensure session policies are in the config for the resumed turn
            config = session.config_override or {}
            policies = self._session_policies.get(social_chat_id)
            if policies:
                config["tool_approval_policy"] = dict(policies)

            full_response = await processor.process_turn_text(
                chat_id=social_chat_id,
                user_id=CONFIG.user_id,
                message_content="",
                resume_approvals=session.to_resume_approvals(),
                config_override=config,
                is_social=True,
            )

            if full_response.strip():
                await self.channel_manager.send_message(
                    session.platform, session.target_id, full_response
                )
        except Exception as e:
            logger.error(f"Failed to resume social chat: {e}")
            await self.channel_manager.send_message(
                session.platform, session.target_id, f"❌ Failed to resume chat: {e}"
            )

    def _ensure_chat_exists(
        self, chat_id: str, message: UnifiedMessage, target_id: str
    ):
        """Ensure a record exists in the DB for this chat."""
        db = get_database()
        chat = db.get_chat(chat_id)
        if not chat:
            is_group = target_id != message.sender_id
            if is_group:
                title = f"Group {target_id} ({message.platform})"
            else:
                title = f"Chat with {message.sender_name} ({message.platform})"
            logger.info(f"Creating new social chat: {title} ({chat_id})")
            db.create_chat(
                title=title,
                config={
                    "platform": message.platform,
                    "sender_id": message.sender_id,
                    "target_id": target_id,
                },
                chat_id=chat_id,
            )
