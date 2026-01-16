"""
Sandbox Manager Module
=======================

Manages isolated sandbox sessions with persistent storage for code execution.

Each chat session gets:
- Private storage at /persistence (isolated per session)
- Shared storage at /shared (accessible by all sessions)

Usage:
------
    from suzent.sandbox import SandboxManager
    
    async with SandboxManager() as manager:
        result = await manager.execute("chat_id", "print('Hello!')")
"""

from __future__ import annotations

import time
import uuid
import asyncio
import threading
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List

import httpx

from suzent.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Constants - Single source of truth for sandbox defaults
# =============================================================================

class Defaults:
    """Default values for sandbox configuration."""
    SERVER_URL = "http://localhost:7263"
    NAMESPACE = "suzent"
    DATA_PATH = "sandbox-data"
    IMAGE = "microsandbox/python"
    MEMORY_MB = 512
    CPUS = 1
    CONTAINER_WORKSPACE = "/workspace"
    RPC_TIMEOUT = 30.0

    # Mount points inside microVM
    PERSISTENCE_MOUNT = "/persistence"  # Per-chat storage
    SHARED_MOUNT = "/shared"             # Shared storage

    # Error patterns that trigger auto-healing (case-insensitive matching)
    AUTO_HEAL_PATTERNS = [
        "timeout",
        "connection",
        "reset",
        "failed to connect",
        "internal server error",
        "sandbox not found",
        "vm unavailable",
        "microvm",
        "unreachable",
        "refused",
        "broken pipe",
        "eof",
        "closed",
    ]


class Language(str, Enum):
    """Supported execution languages."""
    PYTHON = "python"
    NODEJS = "nodejs"
    COMMAND = "command"


# =============================================================================
# Data Classes
# =============================================================================

class ExecutionResult:
    """Result from code execution in sandbox."""
    
    __slots__ = ('success', 'output', 'error', 'exit_code', 'language')
    
    def __init__(
        self,
        success: bool,
        output: str,
        error: Optional[str] = None,
        exit_code: int = 0,
        language: Optional[Language] = None
    ):
        self.success = success
        self.output = output
        self.error = error
        self.exit_code = exit_code
        self.language = language
    
    @classmethod
    def failure(cls, error: str) -> ExecutionResult:
        """Factory for failed execution."""
        return cls(success=False, output="", error=error)
    
    @classmethod
    def from_repl_response(cls, response: dict, language: Language) -> ExecutionResult:
        """Factory from sandbox.repl.run response."""
        if "error" in response:
            return cls.failure(str(response["error"]))
        
        result = response.get("result", {})
        output_parts = []
        
        for chunk in result.get("output", []):
            if isinstance(chunk, dict):
                output_parts.append(chunk.get("text", ""))
            else:
                output_parts.append(str(chunk))
        
        if "text" in result:
            output_parts.append(result["text"])
            
        output = "".join(output_parts).strip()
        
        # Determine success: check has_error flag AND check for common exception patterns in output
        # if the server fails to set has_error correctly for some runtimes.
        success = not result.get("has_error", False)
        
        # Heuristic: If we see a Python traceback or common error marker and success was True,
        # it might be a false positive from the REPL server.
        # However, we should trust 'has_error' primarily. 
        # The 'test_exception_recovery' failure "Exception should fail" suggests 'has_error' was False.
        # Let's verify if the output contains an unhandled exception.
        if success and language == Language.PYTHON:
            if "Traceback (most recent call last):" in output or "SyntaxError:" in output:
                success = False

        return cls(
            success=success,
            output=output,
            error=result.get("error") or (output if not success else None),
            language=language
        )
    
    @classmethod
    def from_command_response(cls, response: dict) -> ExecutionResult:
        """Factory from sandbox.command.run response."""
        if "error" in response:
            return cls.failure(str(response["error"]))
        
        result = response.get("result", {})
        
        # Parse output which can be a list of dicts or a string
        raw_output = result.get("output", "")
        if isinstance(raw_output, list):
            output_parts = []
            for chunk in raw_output:
                if isinstance(chunk, dict):
                    output_parts.append(chunk.get("text", ""))
                else:
                    output_parts.append(str(chunk))
            output = "".join(output_parts)
        else:
            output = str(raw_output)

        return cls(
            success=result.get("success", result.get("exit_code", 0) == 0),
            output=output.strip(),
            error=result.get("error") or None,
            exit_code=result.get("exit_code", 0),
            language=Language.COMMAND
        )


# =============================================================================
# RPC Client
# =============================================================================

class RPCClient:
    """
    JSON-RPC client for microsandbox server.

    Uses httpx with connection pooling if available for better performance,
    falls back to urllib if httpx is not installed.
    """

    def __init__(self, server_url: str, timeout: float = Defaults.RPC_TIMEOUT):
        self.server_url = server_url
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None
        self._lock = threading.Lock()

    @property
    def rpc_url(self) -> str:
        return f"{self.server_url}/api/v1/rpc"

    def _get_client(self) -> httpx.Client:
        """Get or create httpx client with connection pooling."""
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(
                    timeout=httpx.Timeout(self.timeout, connect=10.0),
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                )
            return self._client

    def close(self):
        """Close the httpx client and release connections."""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None

    def call(self, method: str, params: dict, timeout: Optional[float] = None) -> dict:
        """Send JSON-RPC request and return response (synchronous)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": str(uuid.uuid4())
        }

        # Use longer timeout for start operations
        effective_timeout = timeout or self.timeout
        if method == "sandbox.start":
            effective_timeout = max(effective_timeout, 120.0)  # 2 min for start

        try:
            # Prefer httpx for connection pooling
            client = self._get_client()
            return self._httpx_request(client, payload, effective_timeout)
        except Exception as e:
            error_msg = str(e) or repr(e) or type(e).__name__
            logger.error(f"RPC call {method} failed: {error_msg}")
            return {"error": error_msg}

    def _httpx_request(self, client: httpx.Client, payload: dict, timeout: float) -> dict:
        """Make request using httpx with connection pooling."""
        response = client.post(
            self.rpc_url,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    # Async wrapper for backward compatibility
    async def call_async(self, method: str, params: dict, timeout: Optional[float] = None) -> dict:
        """Async wrapper around sync call (runs in thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.call(method, params, timeout))

    def __del__(self):
        """Cleanup httpx client on garbage collection."""
        self.close()


# =============================================================================
# Sandbox Session
# =============================================================================

class SandboxSession:
    """Represents an active sandbox session."""

    def __init__(
        self,
        session_id: str,
        rpc: RPCClient,
        namespace: str,
        data_path: str,
        container_workspace: str,
        image: str,
        memory_mb: int,
        cpus: int,
        custom_volumes: Optional[List[str]] = None
    ):
        self.session_id = session_id
        self.rpc = rpc
        self.namespace = namespace
        self.data_path = data_path
        self.container_workspace = container_workspace
        self.image = image
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.custom_volumes = custom_volumes or []
        self._is_running = False
        self._lock = threading.RLock()  # Reentrant lock for thread safety
    
    @property
    def sandbox_name(self) -> str:
        """Generate sandbox name from session ID."""
        # Keep only alphanumeric characters to ensure valid container/hostname
        safe_id = "".join(c for c in self.session_id if c.isalnum())[:20]
        return f"session-{safe_id}"
    
    @property
    def session_dir(self) -> Path:
        """Host path for session's private storage."""
        return Path(self.data_path) / "sessions" / self.session_id
    
    @property
    def is_running(self) -> bool:
        return self._is_running

    def verify_running(self) -> bool:
        """
        Query server to verify sandbox is actually running.

        Updates _is_running to match actual state, fixing any desynchronization.
        Returns True if sandbox is running on server.
        """
        with self._lock:
            try:
                response = self.rpc.call("sandbox.metrics.get", {
                    "namespace": self.namespace,
                    "sandbox": self.sandbox_name
                }, timeout=5.0)

                # If we get metrics without error, sandbox is running
                actually_running = "error" not in response and response.get("result") is not None

                # Sync state if different
                if self._is_running != actually_running:
                    logger.warning(
                        f"Session {self.session_id} state desync: "
                        f"cached={self._is_running}, actual={actually_running}"
                    )
                    self._is_running = actually_running

                return actually_running
            except Exception as e:
                logger.debug(f"verify_running failed for {self.session_id}: {e}")
                return False
    
    def _get_volume_mounts(self) -> List[str]:
        """Generate volume mount specifications."""
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Default mounts: persistence (per-session) and shared (global)
        # Use configured mount points (defaults: /persistence and /shared)
        volumes = [
            f"{self.container_workspace}/{self.data_path}/sessions/{self.session_id}:{Defaults.PERSISTENCE_MOUNT}",
            f"{self.container_workspace}/{self.data_path}/shared:{Defaults.SHARED_MOUNT}"
        ]
        
        # Add custom volumes from config
        for vol in self.custom_volumes:
            # Prepend container_workspace to host paths for relative paths
            if ':' in vol:
                host, container = vol.split(':', 1)

                # Validate container path uses forward slashes (Linux)
                if '\\' in container:
                    logger.error(f"Invalid volume mount {vol!r}: container path must use forward slashes (/), not backslashes (\\)")
                    continue

                if not host.startswith('/'):
                    host = f"{self.container_workspace}/{host}"
                volumes.append(f"{host}:{container}")
            else:
                logger.warning(f"Invalid volume format (expected host:container): {vol}")
        
        return volumes
    
    def start(self) -> bool:
        """Start the sandbox session."""
        with self._lock:
            if self._is_running:
                return True

            logger.info(f"Starting sandbox session: {self.session_id}")

            # Retry logic for starting sessions under load
            max_retries = 3
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    response = self.rpc.call("sandbox.start", {
                        "namespace": self.namespace,
                        "sandbox": self.sandbox_name,
                        "config": {
                            "image": self.image,
                            "memory": self.memory_mb,
                            "cpus": self.cpus,
                            "volumes": self._get_volume_mounts()
                        }
                    })

                    if "error" in response:
                        last_error = response['error']
                        # If service is busy or temporarily unavailable, wait and retry
                        if attempt < max_retries - 1:
                            time.sleep(1.0 * (attempt + 1))
                            continue
                        logger.error(f"Failed to start session {self.session_id} after {max_retries} attempts: {last_error}")
                        return False
                    
                    self._is_running = True
                    logger.info(f"Sandbox session started: {self.session_id}")
                    return True
                    
                except Exception as e:
                    last_error = str(e)
                    if attempt < max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                        continue
            
            logger.error(f"Failed to start session {self.session_id}: {last_error}")
            return False

    def stop(self) -> bool:
        """Stop the sandbox session."""
        with self._lock:
            if not self._is_running:
                return True
            return self._force_stop()

    def _force_stop(self) -> bool:
        """
        Force stop the sandbox session, ignoring _is_running state.

        Used by auto-healing to ensure sandbox.stop RPC is always called.
        Must be called while holding self._lock.
        """
        logger.info(f"Stopping sandbox session: {self.session_id}")

        response = self.rpc.call("sandbox.stop", {
            "namespace": self.namespace,
            "sandbox": self.sandbox_name
        })

        self._is_running = False
        return "error" not in response
    
    def execute(
        self,
        content: str,
        language: Language = Language.PYTHON,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """Execute code or command in the sandbox."""
        with self._lock:
            if not self._is_running:
                if not self.start():
                    return ExecutionResult.failure("Failed to start sandbox session")

            if language == Language.COMMAND:
                return self._execute_command(content, timeout)
            else:
                return self._execute_code(content, language, timeout)

    def _should_auto_heal(self, error_msg: str) -> bool:
        """Check if error message should trigger auto-healing."""
        error_lower = error_msg.lower()
        return any(pattern in error_lower for pattern in Defaults.AUTO_HEAL_PATTERNS)

    def _execute_code(
        self,
        code: str,
        language: Language,
        timeout: Optional[int]
    ) -> ExecutionResult:
        """Execute code via sandbox.repl.run."""
        params = {
            "namespace": self.namespace,
            "sandbox": self.sandbox_name,
            "language": language.value,
            "code": code
        }
        if timeout:
            params["timeout"] = timeout

        response = self.rpc.call("sandbox.repl.run", params)

        # Auto-healing: If execution fails with recoverable errors,
        # try to restart the session and retry once.
        if "error" in response:
            error_msg = str(response["error"])
            if self._should_auto_heal(error_msg):
                logger.warning(f"Execution failed ({error_msg}), attempting auto-healing for session {self.session_id}...")
                # Force stop first (don't rely on _is_running check)
                self._force_stop()
                if self.start():
                    response = self.rpc.call("sandbox.repl.run", params)
                    if "error" not in response:
                        logger.info(f"Auto-healing successful for session {self.session_id}")
                    else:
                        logger.warning(f"Auto-healing failed, error persists: {response.get('error')}")

        return ExecutionResult.from_repl_response(response, language)
    
    def _execute_command(
        self, 
        content: str,
        timeout: Optional[int]
    ) -> ExecutionResult:
        """
        Execute shell command via Python subprocess (workaround for RPC args bug).
        
        Wraps the command in a Python script and executes via REPL.
        """
        # Split content into command and args
        parts = content.split()
        if not parts:
            return ExecutionResult(success=True, output="", language=Language.COMMAND)
            
        # Construct Python script to run the command
        # We pass the list of parts directly to subprocess.run to avoid shell injection
        # and handle arguments correctly without relying on the broken sandbox.command.run
        py_script = f"""
import subprocess, sys
cmd = {parts}
try:
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout, end='')
    if res.stderr:
        print(res.stderr, file=sys.stderr, end='')
    print(f'\\n__EXIT_CODE__:{{res.returncode}}')
except FileNotFoundError:
    print(f'Command not found: {{cmd[0]}}', file=sys.stderr)
    print('\\n__EXIT_CODE__:127')
except Exception as e:
    print(str(e), file=sys.stderr)
    print('\\n__EXIT_CODE__:1')
"""
        
        # Execute as Python code
        result = self._execute_code(py_script, Language.PYTHON, timeout)
        
        # Parse exit code from output
        output = result.output
        exit_code = 0
        if "__EXIT_CODE__:" in output:
            parts = output.rsplit("__EXIT_CODE__:", 1)
            output = parts[0].strip()
            try:
                exit_code = int(parts[1].strip())
            except ValueError:
                pass
        
        # Convert back to command result format
        return ExecutionResult(
            success=result.success and exit_code == 0,
            output=output,
            error=result.error or (output if exit_code != 0 else None),
            exit_code=exit_code,
            language=Language.COMMAND
        )


# =============================================================================
# Sandbox Manager
# =============================================================================

class SandboxManager:
    """
    Manages isolated sandbox sessions with persistent storage.
    
    Reads configuration from suzent.config.CONFIG as single source of truth.
    Falls back to Defaults if CONFIG not available.
    
    Usage:
        with SandboxManager() as manager:
            result = manager.execute("chat_id", "print('hello')")
    """
    
    def __init__(self, custom_volumes: Optional[List[str]] = None):
        """
        Initialize manager.

        Args:
            custom_volumes: Optional per-chat volume mounts.
                           If None, reads from CONFIG (global config).
        """
        # Import here to avoid circular imports
        from suzent.config import CONFIG

        # Read from CONFIG (single source of truth)
        self.server_url = getattr(CONFIG, 'sandbox_server_url', Defaults.SERVER_URL)
        self.namespace = Defaults.NAMESPACE
        self.data_path = getattr(CONFIG, 'sandbox_data_path', Defaults.DATA_PATH)

        # Use custom_volumes if provided (per-chat), otherwise use global config
        if custom_volumes is not None:
            self.custom_volumes = custom_volumes
        else:
            self.custom_volumes = getattr(CONFIG, 'sandbox_volumes', []) or []

        self.image = Defaults.IMAGE
        self.memory_mb = Defaults.MEMORY_MB
        self.cpus = Defaults.CPUS
        self.container_workspace = Defaults.CONTAINER_WORKSPACE

        self.rpc = RPCClient(self.server_url)
        self._sessions: Dict[str, SandboxSession] = {}
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create storage directory structure."""
        base = Path(self.data_path)
        (base / "shared").mkdir(parents=True, exist_ok=True)
        (base / "sessions").mkdir(parents=True, exist_ok=True)
    
    def __enter__(self) -> SandboxManager:
        return self
    
    def __exit__(self, *args) -> None:
        self.cleanup_all()
    
    def _create_session(self, session_id: str) -> SandboxSession:
        """Factory for creating sessions with current config."""
        return SandboxSession(
            session_id=session_id,
            rpc=self.rpc,
            namespace=self.namespace,
            data_path=self.data_path,
            container_workspace=self.container_workspace,
            image=self.image,
            memory_mb=self.memory_mb,
            cpus=self.cpus,
            custom_volumes=self.custom_volumes
        )
    
    def get_session(self, session_id: str) -> SandboxSession:
        """Get or create a session for the given ID."""
        if session_id not in self._sessions:
            self._sessions[session_id] = self._create_session(session_id)
        return self._sessions[session_id]
    
    def execute(
        self,
        session_id: str,
        content: str,
        language: Language | str = Language.PYTHON,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """
        Execute code or command in a sandbox session.
        
        Args:
            session_id: Session identifier (e.g., chat_id)
            content: Code or command to execute
            language: Execution language (python, nodejs, command)
            timeout: Optional execution timeout in seconds
        """
        if isinstance(language, str):
            try:
                language = Language(language.lower())
            except ValueError:
                return ExecutionResult.failure(f"Unknown language: {language}")
        
        session = self.get_session(session_id)
        return session.execute(content, language, timeout)
    
    def start_session(self, session_id: str) -> bool:
        """Explicitly start a session."""
        return self.get_session(session_id).start()
    
    def stop_session(self, session_id: str) -> bool:
        """Stop a session (preserves persistent data)."""
        if session_id in self._sessions:
            result = self._sessions[session_id].stop()
            del self._sessions[session_id]
            return result
        return True
    
    def cleanup_all(self) -> None:
        """Stop all active sessions and close RPC client."""
        for session_id in list(self._sessions.keys()):
            self.stop_session(session_id)
        # Close httpx connection pool
        self.rpc.close()

    def is_server_available(self) -> bool:
        """Check if sandbox server is reachable."""
        try:
            response = self.rpc.call("sandbox.metrics.get", {"namespace": "*"}, timeout=5.0)
            return "error" not in response
        except Exception:
            return False

    @property
    def active_sessions(self) -> List[str]:
        """Get list of active session IDs."""
        return [sid for sid, s in self._sessions.items() if s.is_running]


# =============================================================================
# Utilities
# =============================================================================

def check_server_status(server_url: Optional[str] = None) -> bool:
    """Check if microsandbox server is running."""
    if server_url is None:
        from suzent.config import CONFIG
        server_url = getattr(CONFIG, 'sandbox_server_url', Defaults.SERVER_URL)

    # Use RPC endpoint since /health returns 404
    rpc = RPCClient(server_url, timeout=5.0)
    try:
        response = rpc.call("sandbox.metrics.get", {"namespace": "*"})
        result = "error" not in response
        rpc.close()  # Clean up
        return result
    except Exception:
        rpc.close()
        return False

