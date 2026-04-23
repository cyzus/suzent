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
from suzent.core.run_state import ChatRunState
from suzent.database import get_database
from suzent.core.stream_registry import (
    register_background_stream,
    unregister_background_stream,
)

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

    # Handshake states per sender key ("platform:sender_id")
    _HANDSHAKE_WAITING = "waiting"  # bot sent the greeting, awaiting user reply
    _HANDSHAKE_PENDING = "pending"  # user replied with intro; awaiting admin approval

    def __init__(
        self,
        channel_manager: ChannelManager,
        allowed_users: list = None,
        platform_allowlists: dict = None,
        model: str = None,
        memory_enabled: bool = True,
        tools: list = None,
        mcp_enabled: dict = None,
        handshake_enabled: bool = False,
        handshake_greeting: str = None,
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
        self._run_states: Dict[str, ChatRunState] = {}  # per social_chat_id
        self._cleanup_task: Optional[asyncio.Task] = None

        # Handshake protocol config
        self.handshake_enabled = handshake_enabled
        self.handshake_greeting = handshake_greeting or (
            "👋 Hi! I'm Suzent. To get access, please introduce yourself — "
            "who are you and what brings you here?"
        )
        # sender_key → {state, sender_id, sender_name, platform, intro, requested_at}
        # This dict is the canonical pairing registry; exposed via REST + CLI.
        self._pending_pairings: Dict[str, dict] = {}

    def update_model(self, model: str):
        """Update the model used for social interactions."""
        self.model = model

    async def start(self):
        """Start the processing loop and cleanup task."""
        await super().start()
        # Start background cleanup task
        self._cleanup_task = asyncio.create_task(self._run_cleanup_loop())

    async def stop(self):
        """Stop the processing loop and cleanup task."""
        # Cancel cleanup task first
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        # Then call parent stop
        await super().stop()

    async def _run_loop(self):
        """Delegate to the queue processor."""
        await self._process_queue()

    def _get_run_state(self, social_chat_id: str) -> ChatRunState:
        """Get or create the run state for a social chat."""
        import time

        if social_chat_id not in self._run_states:
            self._run_states[social_chat_id] = ChatRunState()
        else:
            # Update last activity timestamp
            self._run_states[social_chat_id].last_activity = time.time()
        return self._run_states[social_chat_id]

    def _is_steer(self, message: UnifiedMessage, state: ChatRunState) -> bool:
        """Determine if a message should steer (interrupt) the active run."""
        content_lower = message.content.strip().lower()
        # Explicit /steer or /redirect command always steers
        if content_lower.startswith("/steer") or content_lower.startswith("/redirect"):
            return True
        # Same sender as active run = implicit steer
        if message.sender_id == state.active_sender:
            return True
        return False

    async def _cancel_active(self, social_chat_id: str, state: ChatRunState):
        """Cancel the active task and wait for it to finish."""
        from suzent.core.run_state import cancel_and_wait

        await cancel_and_wait(social_chat_id)
        if state.active_task and not state.active_task.done():
            state.active_task.cancel()
            try:
                await state.active_task
            except (asyncio.CancelledError, Exception):
                pass
        state.active_task = None
        state.active_sender = None

    async def _process_queue(self):
        """Main loop consuming messages with managed run states."""
        while self._running:
            try:
                message: UnifiedMessage = await self.channel_manager.message_queue.get()
                # Route message through managed state instead of fire-and-forget
                asyncio.create_task(self._route_message(message))
                self.channel_manager.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SocialBrain loop: {e}")
                await asyncio.sleep(1)

    def _sender_key(self, message: UnifiedMessage) -> str:
        return f"{message.platform}:{message.sender_id}"

    async def _route_message(self, message: UnifiedMessage):
        """Route a message through the run state manager: steer, queue, or process."""
        # Handshake protocol: intercept unauthorized users before the hard deny
        if self.handshake_enabled and not self._is_authorized(message):
            await self._handle_handshake(message)
            return

        # Auth and command dispatch happen before run state management
        if not self._is_authorized(message):
            logger.warning(
                f"Unauthorized social message from: {message.sender_name} ({message.sender_id}) on {message.platform}"
            )
            await self.channel_manager.send_message(
                message.platform,
                message.sender_id,
                "Access Denied. You are not authorized to use this bot.",
            )
            return

        from suzent.channels.utils import extract_target_id

        target_id = extract_target_id(message)
        default_chat_id = f"social-{message.platform}-{target_id}"

        # Unified slash command dispatch
        from suzent.core.commands import dispatch as dispatch_command, CommandContext
        from suzent.core.commands.sess import get_active_chat_id

        ctx = CommandContext(
            chat_id=default_chat_id,
            user_id="default-user",
            platform=message.platform,
            sender_id=message.sender_id,
            channel_manager=self.channel_manager,
        )
        cmd_result = await dispatch_command(ctx, message.content)
        if cmd_result is not None:
            if cmd_result:  # empty string means handler sent its own reply
                await self.channel_manager.send_message(
                    message.platform, message.sender_id, cmd_result
                )
            return

        # Resolve active chat (may have been switched via /sess)
        social_chat_id = get_active_chat_id(message.sender_id, default_chat_id)

        state = self._get_run_state(social_chat_id)

        # Check state under lock
        async with state.lock:
            if state.active_task and not state.active_task.done():
                # There IS an active run
                if self._is_steer(message, state):
                    # STEER: cancel current run, process this message
                    # Mark that we're steering (claim the slot before releasing lock)
                    task_to_cancel = state.active_task
                    state.active_task = (
                        None  # Prevent other messages from seeing active task
                    )
                    state.active_sender = None
                    self._sessions.pop(social_chat_id, None)
                else:
                    # QUEUE: hold until current run finishes
                    state.queued_messages.append(message)
                    return
            elif social_chat_id in self._sessions:
                # Pending approval session active
                if self._is_steer(message, state):
                    self._sessions.pop(social_chat_id)
                    task_to_cancel = None
                    # Fall through to process as new turn
                else:
                    state.queued_messages.append(message)
                    return
            else:
                task_to_cancel = None

        # Cancel outside the lock to prevent deadlock
        # (task's finally block also acquires the lock)
        if task_to_cancel:
            await self._cancel_active(social_chat_id, state)

        # Re-acquire lock to start new task atomically
        async with state.lock:
            # Double-check no one else started a task while we were canceling
            if state.active_task and not state.active_task.done():
                # Another message snuck in, queue this one
                state.queued_messages.append(message)
                return

            # Process this message (either fresh or post-steer)
            state.active_sender = message.sender_id
            state.active_task = asyncio.create_task(
                self._process_and_drain(social_chat_id, message, state)
            )

    async def _process_and_drain(
        self, social_chat_id: str, message: UnifiedMessage, state: ChatRunState
    ):
        """Process a message turn and then drain any queued messages."""
        try:
            await self._handle_message(message, social_chat_id=social_chat_id)
        except Exception as e:
            logger.error(f"Error handling social message in managed task: {e}")
        finally:
            async with state.lock:
                while state.queued_messages:
                    next_msg = state.queued_messages.pop(0)
                    state.active_sender = next_msg.sender_id
                    try:
                        await self._handle_message(
                            next_msg, social_chat_id=social_chat_id
                        )
                    except Exception as e:
                        logger.error(f"Error handling queued message: {e}")
                state.active_task = None
                state.active_sender = None

    async def _run_cleanup_loop(self):
        """Background task to periodically clean up stale run states."""
        cleanup_interval = 300  # 5 minutes
        ttl_seconds = 3600  # 1 hour

        while self._running:
            try:
                await asyncio.sleep(cleanup_interval)

                # Clean up local _run_states
                import time

                current_time = time.time()
                stale_chat_ids = []

                for chat_id, state in self._run_states.items():
                    # Don't clean up if there's an active task
                    if state.active_task and not state.active_task.done():
                        continue

                    # Check if state is stale
                    if current_time - state.last_activity > ttl_seconds:
                        stale_chat_ids.append(chat_id)

                # Remove stale states
                for chat_id in stale_chat_ids:
                    del self._run_states[chat_id]

                if stale_chat_ids:
                    logger.debug(
                        f"Cleaned up {len(stale_chat_ids)} stale run states "
                        f"(TTL: {ttl_seconds}s)"
                    )

                # Also clean up global run states
                from suzent.core.run_state import cleanup_stale_states

                global_cleaned = cleanup_stale_states(ttl_seconds)
                if global_cleaned:
                    logger.debug(
                        f"Cleaned up {global_cleaned} global run states "
                        f"(TTL: {ttl_seconds}s)"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    # ------------------------------------------------------------------ #
    # Pairing / handshake protocol                                        #
    # ------------------------------------------------------------------ #

    async def _handle_handshake(self, message: UnifiedMessage):
        """
        Two-step pairing flow for unknown users:
          1. First contact → send greeting, record state=waiting
          2. User replies with intro → state=pending; admin approves via UI or CLI
        """
        import time

        key = self._sender_key(message)
        entry = self._pending_pairings.get(key)
        content = message.content.strip()

        if entry is None:
            # First contact — send greeting and park in "waiting"
            self._pending_pairings[key] = {
                "state": self._HANDSHAKE_WAITING,
                "sender_id": message.sender_id,
                "sender_name": message.sender_name,
                "platform": message.platform,
                "intro": "",
                "requested_at": time.time(),
            }
            await self.channel_manager.send_message(
                message.platform, message.sender_id, self.handshake_greeting
            )
            return

        if entry["state"] == self._HANDSHAKE_WAITING:
            # User replied with their intro → promote to pending (awaiting admin)
            entry["state"] = self._HANDSHAKE_PENDING
            entry["intro"] = content
            await self.channel_manager.send_message(
                message.platform,
                message.sender_id,
                "✅ Thanks! Your request has been sent for review. Please wait.",
            )
            return

        # Already pending
        await self.channel_manager.send_message(
            message.platform,
            message.sender_id,
            "⏳ Your access request is still pending admin approval.",
        )

    # -- Public API (called by REST routes and CLI) -- #

    def list_pairings(self) -> list[dict]:
        """Return all pending pairing requests as a list of dicts."""
        return [
            {
                "key": key,
                "sender_id": e["sender_id"],
                "sender_name": e["sender_name"],
                "platform": e["platform"],
                "intro": e["intro"],
                "state": e["state"],
                "requested_at": e["requested_at"],
            }
            for key, e in self._pending_pairings.items()
        ]

    async def approve_pairing(self, sender_id: str) -> bool:
        """Approve a pending pairing request by sender_id."""
        matched_key = next(
            (
                k
                for k, e in self._pending_pairings.items()
                if e["sender_id"] == sender_id
            ),
            None,
        )
        if not matched_key:
            return False

        entry = self._pending_pairings.pop(matched_key)
        self.allowed_users.add(entry["sender_id"])
        self.allowed_users.add(entry["sender_name"])
        await self._persist_approved_user(entry["sender_id"])

        try:
            await self.channel_manager.send_message(
                entry["platform"],
                entry["sender_id"],
                "✅ Your access has been approved! You can now send messages.",
            )
        except Exception:
            pass
        logger.info(
            f"Pairing approved: {entry['sender_id']} ({entry['sender_name']}) on {entry['platform']}"
        )
        return True

    async def deny_pairing(self, sender_id: str) -> bool:
        """Deny a pending pairing request by sender_id."""
        matched_key = next(
            (
                k
                for k, e in self._pending_pairings.items()
                if e["sender_id"] == sender_id
            ),
            None,
        )
        if not matched_key:
            return False

        entry = self._pending_pairings.pop(matched_key)
        try:
            await self.channel_manager.send_message(
                entry["platform"],
                entry["sender_id"],
                "❌ Your access request was not approved.",
            )
        except Exception:
            pass
        logger.info(
            f"Pairing denied: {entry['sender_id']} ({entry['sender_name']}) on {entry['platform']}"
        )
        return True

    async def _persist_approved_user(self, sender_id: str):
        """Persist an approved sender_id to social.json so it survives restarts."""
        try:
            import json as _json
            from suzent.config import PROJECT_DIR

            config_path = PROJECT_DIR / "config" / "social.json"
            if not config_path.exists():
                return
            with open(config_path) as f:
                cfg = _json.load(f)
            users = cfg.get("allowed_users", [])
            if sender_id not in users:
                users.append(sender_id)
            cfg["allowed_users"] = users
            with open(config_path, "w") as f:
                _json.dump(cfg, f, indent=2)
        except Exception as e:
            logger.warning(f"Pairing: could not persist approval: {e}")

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

    async def _handle_message(
        self, message: UnifiedMessage, social_chat_id: str | None = None
    ):
        """
        Handle a single message using ChatProcessor.
        Auth and command dispatch are handled by _route_message before this is called.
        """
        try:
            # 1. Resolve Chat ID and target
            from suzent.channels.utils import extract_target_id

            target_id = extract_target_id(message)
            if social_chat_id is None:
                social_chat_id = f"social-{message.platform}-{target_id}"
            self._ensure_chat_exists(social_chat_id, message, target_id)

            # Check if this is a steer (content may have been rewritten by /steer command)
            content_lower = message.content.strip().lower()
            is_steer = content_lower.startswith("/steer") or content_lower.startswith(
                "/redirect"
            )
            steer_text = message.content.strip()
            if is_steer:
                # Strip the command prefix
                if content_lower.startswith("/redirect"):
                    steer_text = steer_text[len("/redirect") :].strip()
                else:
                    steer_text = steer_text[len("/steer") :].strip()
                if not steer_text:
                    await self.channel_manager.send_message(
                        message.platform,
                        target_id,
                        "Usage: /steer <your redirection message>",
                    )
                    return

            logger.info(
                f"Processing social message for {social_chat_id}: {message.content}"
            )

            # 2. Slash command dispatch — runs on the raw content before envelope wrapping
            # so that dispatch() can detect the leading "/" and surface check works.
            if not is_steer and message.content.strip().startswith("/"):
                from suzent.core.commands import (
                    dispatch as _dispatch_command,
                    CommandContext as _CmdCtx,
                )
                from suzent.core.chat_processor import _append_command_messages

                cmd_result = await _dispatch_command(
                    _CmdCtx(
                        chat_id=social_chat_id, user_id=CONFIG.user_id, surface="social"
                    ),
                    message.content.strip(),
                )
                if cmd_result is not None:
                    try:
                        from suzent.database import get_database as _get_db

                        _db = _get_db()
                        _chat = _db.get_chat(social_chat_id)
                        if _chat is not None:
                            updated = _append_command_messages(
                                list(_chat.messages or []),
                                message.content.strip(),
                                cmd_result,
                            )
                            _db.update_chat(social_chat_id, messages=updated)
                    except Exception:
                        pass
                    await self.channel_manager.send_message(
                        message.platform, target_id, cmd_result
                    )
                    return

            # 3. Envelope header — prepend platform metadata to message
            envelope = f"[{message.platform.title()} {message.sender_name} id:{message.sender_id}]"
            enriched_content = (
                f"{envelope}\n{steer_text if is_steer else message.content}"
            )

            # 3. Setup Processor
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
            else:
                # "All Tools" mode: pass the full registry list so build_agent_config
                # doesn't fall back to the narrower default_tools subset.
                if CONFIG.tool_options:
                    base_config["tools"] = list(CONFIG.tool_options)

            config_override = build_agent_config(base_config, require_social_tool=False)

            # Inject any session-level tool approval policies
            policies = self._session_policies.get(social_chat_id)
            if policies:
                config_override["tool_approval_policy"] = dict(policies)

            # 4. Process and Reply — collect all approval requests from the stream
            collected_approvals: list[ApprovalRequest] = []

            async def on_event(event):
                if isinstance(event, ApprovalRequest):
                    logger.info(
                        f"SocialBrain: Collected approval request for {event.tool_name}"
                    )
                    collected_approvals.append(event)

            stream_queue = register_background_stream(social_chat_id)

            # Check if this channel supports streaming
            channel = self.channel_manager.channels.get(message.platform)
            supports_streaming = hasattr(channel, "send_stream")

            if supports_streaming and not is_steer:
                # Run the LLM turn concurrently while piping text deltas to the channel
                import json as _json

                async def _text_delta_stream():
                    """Yield text deltas from the background stream queue."""
                    while True:
                        chunk = await stream_queue.get()
                        if chunk is None:  # sentinel
                            break
                        try:
                            if chunk.startswith("data: "):
                                data = _json.loads(chunk[6:].strip())
                                if data.get("type") == "TEXT_MESSAGE_CONTENT":
                                    delta = data.get("delta", "")
                                    if delta:
                                        yield delta
                        except Exception:
                            pass

                # Start the LLM turn as a background task
                process_task = asyncio.create_task(
                    processor.process_turn_text(
                        chat_id=social_chat_id,
                        user_id=CONFIG.user_id,
                        message_content=enriched_content,
                        files=message.attachments,
                        config_override=config_override,
                        on_event=on_event,
                        _stream_queue=stream_queue,
                    )
                )

                try:
                    await self.channel_manager.send_stream(
                        message.platform, target_id, _text_delta_stream()
                    )
                    full_response = await process_task
                except Exception:
                    process_task.cancel()
                    raise
                finally:
                    unregister_background_stream(social_chat_id)
            else:
                try:
                    if is_steer:
                        full_response = await processor.process_steer_text(
                            chat_id=social_chat_id,
                            user_id=CONFIG.user_id,
                            steer_message=enriched_content,
                            config_override=config_override,
                            on_event=on_event,
                            _stream_queue=stream_queue,
                        )
                    else:
                        full_response = await processor.process_turn_text(
                            chat_id=social_chat_id,
                            user_id=CONFIG.user_id,
                            message_content=enriched_content,
                            files=message.attachments,
                            config_override=config_override,
                            on_event=on_event,
                            _stream_queue=stream_queue,
                        )
                finally:
                    unregister_background_stream(social_chat_id)

            try:
                get_database().set_last_result_at(social_chat_id)
            except Exception:
                pass

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

            # Send Final Response (non-streaming path, or steer)
            if not supports_streaming and full_response.strip():
                await self.channel_manager.send_message(
                    message.platform, target_id, full_response
                )
            elif is_steer and full_response.strip():
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
