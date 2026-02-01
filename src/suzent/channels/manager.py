"""
Manager for social messaging channels.
Responsible for driver registry and message routing.
"""

import asyncio
import os
from typing import Dict, Optional, List
from suzent.logger import get_logger
from suzent.channels.base import SocialChannel, UnifiedMessage

logger = get_logger(__name__)


class ChannelManager:
    """
    Central coordinator for all social channels.
    """

    def __init__(self):
        self.channels: Dict[str, SocialChannel] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    def load_drivers_from_config(self, social_config: Dict):
        """
        Dynamically load channel drivers based on configuration.
        """
        import importlib
        
        # Mapping of config key to module.class
        # This could also be discovered, but a map is safer for now.
        driver_map = {
            "telegram": "suzent.channels.telegram.TelegramChannel",
            "feishu": "suzent.channels.feishu.FeishuChannel",
            # Add future drivers here
        }

        for platform, settings in social_config.items():
            if platform in driver_map and isinstance(settings, dict):
                # Check enabled status (default True if present, but some require explicit enable)
                if not settings.get("enabled", True):
                    continue
                
                # Check required credentials exist
                # (Driver should validate this, but we can do a quick check to avoid useless imports)
                
                module_path, class_name = driver_map[platform].rsplit(".", 1)
                try:
                    module = importlib.import_module(module_path)
                    channel_class = getattr(module, class_name)
                    
                    # Instantiate with settings
                    # Adjust constructor to accept config dict?
                    # TelegramChannel currently takes just token.
                    # We should standardize constructor or handle variations.
                    
                    # Standardization attempt: try passing config dict if constructor supports it,
                    # else fallback to specific fields.
                    
                    if platform == "telegram":
                        token = os.environ.get("TELEGRAM_TOKEN") or settings.get("token")
                        if token:
                            channel = channel_class(token)
                            self.register_channel(channel)
                    
                    elif platform == "feishu":
                         # Feishu needs app_id, app_secret
                         # Let's assume FeishuChannel takes the config dict or specific args
                         # We'll design FeishuChannel to take kwargs or config
                         channel = channel_class(settings) # Pass full settings dict
                         self.register_channel(channel)

                except ImportError:
                    logger.warning(f"Could not load driver for {platform}: Module {module_path} not found.")
                except Exception as e:
                    logger.error(f"Failed to initialize {platform} driver: {e}")

    def register_channel(self, channel: SocialChannel):
        """Add a channel driver to the manager."""
        logger.info(f"Registering social channel: {channel.name}")
        self.channels[channel.name] = channel
        channel.set_callback(self.handle_incoming_message)

    async def handle_incoming_message(self, message: UnifiedMessage):
        """Callback for drivers to push messages into the central queue."""
        logger.debug(f"Received message from {message.platform}: {message.sender_name} - {message.content[:50]}...")
        await self.message_queue.put(message)

    async def start_all(self):
        """Connect all registered channels."""
        self._running = True
        logger.info("Starting all social channels...")
        tasks = []
        for name, channel in self.channels.items():
            tasks.append(self._start_channel(channel))
        
        if tasks:
            await asyncio.gather(*tasks)

    async def _start_channel(self, channel: SocialChannel):
        try:
            await channel.connect()
            logger.info(f"Channel {channel.name} connected.")
        except Exception as e:
            logger.error(f"Failed to connect channel {channel.name}: {e}")

    async def stop_all(self):
        """Disconnect all registered channels."""
        self._running = False
        logger.info("Stopping all social channels...")
        tasks = []
        for name, channel in self.channels.items():
            tasks.append(channel.disconnect())

        if tasks:
            await asyncio.gather(*tasks)

    async def _route_to_channel(self, platform: str, action: str, method_name: str, *args, **kwargs) -> bool:
        """Helper to route actions to the correct channel driver."""
        channel = self.channels.get(platform)
        if not channel:
            logger.error(f"Cannot {action}: Platform '{platform}' not configured.")
            return False

        try:
            method = getattr(channel, method_name)
            return await method(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error {action} on {platform}: {e}")
            return False

    async def send_message(self, platform: str, target_id: str, content: str, **kwargs) -> bool:
        """Route outgoing message to the correct driver."""
        return await self._route_to_channel(
            platform, "send message", "send_message", target_id, content, **kwargs
        )

    async def send_file(self, platform: str, target_id: str, file_path: str, caption: str = None, **kwargs) -> bool:
        """Route outgoing file to the correct driver."""
        return await self._route_to_channel(
            platform, "send file", "send_file", target_id, file_path, caption=caption, **kwargs
        )
