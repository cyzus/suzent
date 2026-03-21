"""
Sandbox Module
==============

Docker-based isolated code execution with session persistence.

Configuration is read from suzent.config.CONFIG (single source of truth).

Usage:
    from suzent.sandbox import SandboxManager, Language

    with SandboxManager() as manager:
        result = manager.execute("chat_id", "print('Hello!')")
        result = manager.execute("chat_id", "ls -la", Language.COMMAND)
"""

from .manager import (
    # Core classes
    SandboxManager,
    DockerSession,
    ExecutionResult,
    # Enums
    Language,
    # Constants
    Defaults,
    # Utilities
    check_docker_available,
)

__all__ = [
    "SandboxManager",
    "DockerSession",
    "ExecutionResult",
    "Language",
    "Defaults",
    "check_docker_available",
]
