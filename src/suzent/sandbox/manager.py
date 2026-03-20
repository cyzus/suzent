"""
Sandbox Manager Module
=======================

Docker-based isolated sandbox for code execution.

Each chat session gets its own container:
- Private storage at /persistence (isolated per session, bind-mounted from host)
- Shared storage at /shared (accessible by all sessions, bind-mounted from host)

Data persists on the host filesystem independent of container lifecycle.

Usage:
    from suzent.sandbox import SandboxManager

    with SandboxManager() as manager:
        result = manager.execute("chat_id", "print('Hello!')")
        result = manager.execute("chat_id", "ls -la", Language.COMMAND)
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

_orphan_cleanup_done = False


# =============================================================================
# Constants
# =============================================================================


class Defaults:
    """Default values for sandbox configuration."""

    IMAGE = "python:3.11-slim"
    MEMORY_MB = 512
    CPUS = 1
    NETWORK = "bridge"
    PIDS_LIMIT = 256
    EXEC_TIMEOUT = 30  # seconds
    IDLE_CLEANUP_INTERVAL = 300  # seconds between idle checks (5 min)
    HOT_WINDOW_SECONDS = 300  # don't recreate containers used within this window

    # Mount points inside container
    PERSISTENCE_MOUNT = "/persistence"
    SHARED_MOUNT = "/shared"

    # Error patterns that trigger auto-healing (container-level errors)
    AUTO_HEAL_PATTERNS = [
        "not running",
        "no such container",
        "connection",
        "timeout",
        "reset",
        "eof",
        "broken pipe",
        "closed",
    ]

    # Host paths blocked from bind mounting (security)
    BLOCKED_MOUNT_PATHS = {
        "/etc",
        "/private/etc",
        "/proc",
        "/sys",
        "/dev",
        "/root",
        "/boot",
        "/run",
        "/var/run",
        "/var/run/docker.sock",
        "/run/docker.sock",
        "/private/var/run",
        "/private/var/run/docker.sock",
        "//./pipe/docker_engine",  # Windows Docker socket
    }

    # Env var patterns blocked from container injection (security)
    BLOCKED_ENV_SUFFIXES = (
        "_API_KEY",
        "_TOKEN",
        "_PASSWORD",
        "_SECRET",
        "_PRIVATE_KEY",
        "_CREDENTIALS",
        "_AUTH",
    )
    BLOCKED_ENV_EXACT = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "COHERE_API_KEY",
        "MISTRAL_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "SLACK_BOT_TOKEN",
        "SLACK_APP_TOKEN",
    }


class Language(str, Enum):
    """Supported execution languages."""

    PYTHON = "python"
    NODEJS = "nodejs"
    COMMAND = "command"


# =============================================================================
# Security helpers
# =============================================================================


def _filter_env_vars(env: dict) -> dict:
    """
    Remove secret-looking env vars before injecting into a container.
    Logs a warning for each dropped key.
    """
    safe = {}
    for key, value in env.items():
        upper = key.upper()
        if upper in Defaults.BLOCKED_ENV_EXACT or any(
            upper.endswith(s) for s in Defaults.BLOCKED_ENV_SUFFIXES
        ):
            logger.warning(f"Sandbox: blocked env var '{key}' — looks like a secret")
            continue
        safe[key] = value
    return safe


def _validate_volume_mount(host_path: str) -> None:
    """
    Raise ValueError if host_path resolves to a dangerous system path.
    Resolves symlinks through existing ancestors before checking.
    """
    try:
        resolved = str(Path(host_path).resolve())
    except Exception:
        resolved = host_path

    resolved_lower = resolved.replace("\\", "/")

    for blocked in Defaults.BLOCKED_MOUNT_PATHS:
        blocked_norm = blocked.replace("\\", "/")
        if resolved_lower == blocked_norm or resolved_lower.startswith(
            blocked_norm.rstrip("/") + "/"
        ):
            raise ValueError(
                f"Sandbox: bind mount to '{host_path}' is not allowed "
                f"(resolves to blocked path '{resolved}')"
            )


# =============================================================================
# Data Classes
# =============================================================================


class ExecutionResult:
    """Result from code execution in sandbox."""

    __slots__ = ("success", "output", "error", "exit_code", "language")

    def __init__(
        self,
        success: bool,
        output: str,
        error: Optional[str] = None,
        exit_code: int = 0,
        language: Optional[Language] = None,
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


# =============================================================================
# Docker Session
# =============================================================================


class DockerSession:
    """
    A persistent Docker container for one chat session.

    Container is created on first use and kept running with 'sleep infinity'.
    Commands are exec'd into it, preserving state between calls.
    Data at /persistence and /shared is bind-mounted from the host, so it
    survives container stop/remove.
    """

    def __init__(
        self,
        session_id: str,
        client,  # docker.DockerClient
        data_path: str,
        image: str,
        memory_mb: int,
        cpus: int,
        network: str,
        setup_command: str = "",
        env: Optional[Dict[str, str]] = None,
        custom_volumes: Optional[List[str]] = None,
    ):
        self.session_id = session_id
        self._client = client
        self.data_path = data_path
        self.image = image
        self.memory_mb = memory_mb
        self.cpus = cpus
        self.network = network
        self.setup_command = setup_command.strip()
        self.env = _filter_env_vars(env or {})
        self.custom_volumes = custom_volumes or []
        self._container = None
        self._is_running = False
        self._lock = threading.RLock()
        self.last_used: float = (
            0.0  # updated on each execute(); 0 = never used this process
        )

    @property
    def container_name(self) -> str:
        safe_id = "".join(c for c in self.session_id if c.isalnum())[:20]
        return f"suzent-sandbox-{safe_id}"

    @property
    def session_dir(self) -> Path:
        return Path(self.data_path) / "sessions" / self.session_id

    @property
    def is_running(self) -> bool:
        return self._is_running

    # -------------------------------------------------------------------------
    # Runtime environment
    # -------------------------------------------------------------------------

    def _build_env(self) -> dict:
        """
        Merge user-supplied env vars with SUZENT_BASE_URL so code inside the
        container can reach the running host server via the Docker bridge.

        host.docker.internal resolves to the host on Docker Desktop (Win/Mac).
        On Linux we add extra_hosts so it resolves the same way.
        """
        import re

        from suzent.config import CONFIG, DATA_DIR

        env = dict(self.env)

        # Start from CONFIG.server_url (e.g. http://localhost:25314/chat),
        # strip the path to get the base (e.g. http://localhost:25314)
        raw = CONFIG.server_url
        match = re.match(r"(https?://[^/]+)", raw)
        base_url = match.group(1) if match else raw

        # Swap localhost/127.0.0.1 → host.docker.internal for Docker routing
        base_url = re.sub(r"localhost|127\.0\.0\.1", "host.docker.internal", base_url)

        # Override port when server started with SUZENT_PORT=0 (dynamic port)
        try:
            port_file = DATA_DIR / "server.port"
            if port_file.exists():
                port = port_file.read_text(encoding="utf-8").strip()
                base_url = re.sub(r":\d+$", f":{port}", base_url)
        except Exception:
            pass

        env["SUZENT_BASE_URL"] = base_url
        return env

    # -------------------------------------------------------------------------
    # Config hash (items 2 + 6)
    # -------------------------------------------------------------------------

    def _compute_config_hash(self) -> str:
        """
        SHA-256 of the container's full config. Stored as a Docker label so we
        can detect stale containers and recreate when config changes.
        """
        data = {
            "image": self.image,
            "network": self.network,
            "memory_mb": self.memory_mb,
            "cpus": self.cpus,
            "volumes": sorted(self.custom_volumes),
            "setup_command": self.setup_command,
            "env_keys": sorted(self.env.keys()),
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[
            :16
        ]

    # -------------------------------------------------------------------------
    # Volume building (item 4)
    # -------------------------------------------------------------------------

    def _build_volumes(self) -> dict:
        """Build Docker volume mount dict from host paths, with security validation."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        shared_dir = Path(self.data_path) / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)

        volumes: dict = {
            str(self.session_dir.resolve()): {
                "bind": Defaults.PERSISTENCE_MOUNT,
                "mode": "rw",
            },
            str(shared_dir.resolve()): {
                "bind": Defaults.SHARED_MOUNT,
                "mode": "rw",
            },
        }

        from suzent.tools.path_resolver import PathResolver

        for vol in self.custom_volumes:
            parsed = PathResolver.parse_volume_string(vol)
            if not parsed:
                logger.warning(f"Skipping invalid volume: {vol}")
                continue
            host, container = parsed
            if not Path(host).is_absolute():
                from suzent.config import PROJECT_DIR

                host = str((PROJECT_DIR / host).resolve())
            try:
                _validate_volume_mount(host)
            except ValueError as e:
                logger.error(str(e))
                continue
            volumes[host] = {"bind": container, "mode": "rw"}

        return volumes

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> bool:
        """Get or create and start the container."""
        with self._lock:
            if self._is_running:
                return True

            import docker
            import docker.errors

            logger.info(f"Starting sandbox container: {self.container_name}")
            current_hash = self._compute_config_hash()

            # Check for existing container
            try:
                container = self._client.containers.get(self.container_name)
                stored_hash = container.labels.get("suzent.config_hash", "")

                if stored_hash and stored_hash != current_hash:
                    # Config changed — hot window check (item 6)
                    age_since_last_use = time.time() - self.last_used
                    if age_since_last_use < Defaults.HOT_WINDOW_SECONDS:
                        logger.warning(
                            f"Container {self.container_name} config has changed "
                            f"but was used {age_since_last_use:.0f}s ago — "
                            f"keeping until idle. Restart the chat to apply changes."
                        )
                    else:
                        logger.info(
                            f"Container {self.container_name} config changed, recreating."
                        )
                        container.remove(force=True)
                        raise docker.errors.NotFound("recreating")

                if container.status == "running":
                    self._container = container
                    self._is_running = True
                    return True

                logger.info(f"Restarting stopped container {self.container_name}")
                container.start()
                self._container = container
                self._is_running = True
                return True

            except docker.errors.NotFound:
                pass

            # Create new container
            try:
                try:
                    self._client.images.get(self.image)
                except docker.errors.ImageNotFound:
                    logger.info(f"Pulling image {self.image}...")
                    self._client.images.pull(self.image)

                container = self._client.containers.create(
                    image=self.image,
                    command="sleep infinity",
                    name=self.container_name,
                    detach=True,
                    mem_limit=f"{self.memory_mb}m",
                    memswap_limit=f"{self.memory_mb}m",
                    nano_cpus=int(self.cpus * 1_000_000_000),
                    pids_limit=Defaults.PIDS_LIMIT,
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    network_mode=self.network,
                    working_dir=Defaults.PERSISTENCE_MOUNT,
                    environment=self._build_env(),
                    # Allow host.docker.internal to resolve on Linux (no-op on Docker Desktop)
                    extra_hosts={"host.docker.internal": "host-gateway"},
                    volumes=self._build_volumes(),
                    labels={
                        "suzent.sandbox": "true",
                        "suzent.session_id": self.session_id,
                        "suzent.created_at": str(int(time.time())),
                        "suzent.config_hash": current_hash,
                    },
                )
                container.start()
                self._container = container
                self._is_running = True
                logger.info(f"Container started: {self.container_name}")

                # Run setup command once on fresh creation (item 1)
                if self.setup_command:
                    logger.info(
                        f"Running setup command for {self.container_name}: "
                        f"{self.setup_command!r}"
                    )
                    result = container.exec_run(
                        ["sh", "-lc", self.setup_command],
                        workdir=Defaults.PERSISTENCE_MOUNT,
                    )
                    if result.exit_code != 0:
                        output = result.output.decode("utf-8", errors="replace").strip()
                        logger.warning(
                            f"Setup command exited {result.exit_code}: {output}"
                        )

                return True

            except Exception as e:
                logger.error(f"Failed to start container {self.container_name}: {e}")
                return False

    def stop(self) -> bool:
        """Stop the container (data on host persists, can resume later)."""
        with self._lock:
            if not self._is_running and self._container is None:
                return True
            try:
                if self._container is None:
                    self._container = self._client.containers.get(self.container_name)
                self._container.stop(timeout=5)
                self._is_running = False
                logger.info(f"Container stopped: {self.container_name}")
                return True
            except Exception as e:
                logger.debug(f"Stop {self.container_name}: {e}")
                self._is_running = False
                return False

    def remove(self) -> bool:
        """Stop and remove the container (host data persists)."""
        with self._lock:
            import docker
            import docker.errors

            try:
                if self._container is None:
                    try:
                        self._container = self._client.containers.get(
                            self.container_name
                        )
                    except docker.errors.NotFound:
                        return True
                self._container.remove(force=True)
                self._container = None
                self._is_running = False
                logger.info(f"Container removed: {self.container_name}")
                return True
            except Exception as e:
                logger.debug(f"Remove {self.container_name}: {e}")
                return False

    def verify_running(self) -> bool:
        """Check actual container state from Docker daemon."""
        with self._lock:
            import docker
            import docker.errors

            try:
                container = self._client.containers.get(self.container_name)
                actually_running = container.status == "running"
                if self._is_running != actually_running:
                    logger.warning(
                        f"Container {self.container_name} state desync: "
                        f"cached={self._is_running}, actual={container.status}"
                    )
                    self._is_running = actually_running
                    if actually_running:
                        self._container = container
                return actually_running
            except docker.errors.NotFound:
                if self._is_running:
                    logger.warning(
                        f"Container {self.container_name} missing, was marked running"
                    )
                self._is_running = False
                return False

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    def execute(
        self,
        content: str,
        language: Language = Language.PYTHON,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute code or command in the container."""
        with self._lock:
            self.last_used = time.time()

            if not self._is_running:
                if not self.start():
                    return ExecutionResult.failure("Failed to start sandbox container")

            try:
                if language == Language.COMMAND:
                    return self._execute_command(content, timeout)
                return self._execute_code(content, language, timeout)
            except TimeoutError as e:
                return ExecutionResult.failure(str(e))
            except Exception as e:
                if self._should_auto_heal(str(e)):
                    logger.warning(
                        f"Container error ({e}), auto-healing session {self.session_id}"
                    )
                    self._is_running = False
                    self._container = None
                    if self.start():
                        try:
                            if language == Language.COMMAND:
                                return self._execute_command(content, timeout)
                            return self._execute_code(content, language, timeout)
                        except Exception as e2:
                            return ExecutionResult.failure(f"Auto-heal failed: {e2}")
                return ExecutionResult.failure(str(e))

    def start_background(
        self,
        content: str,
        language: Language = Language.PYTHON,
    ) -> str:
        """
        Start a long-running process in the background.
        Returns a process_id to poll/kill via ProcessTool.
        """
        with self._lock:
            self.last_used = time.time()

            if not self._is_running:
                if not self.start():
                    raise RuntimeError("Failed to start sandbox container")

        proc_id = uuid.uuid4().hex[:12]

        if language == Language.PYTHON:
            actual_cmd = ["python3", "-c", content]
        elif language == Language.NODEJS:
            actual_cmd = ["node", "-e", content]
        else:
            actual_cmd = ["bash", "-c", content]

        supervisor = f"""
import subprocess, os
proc_id = {proc_id!r}
log_path  = f"/tmp/suzent_proc_{{proc_id}}.log"
pid_path  = f"/tmp/suzent_proc_{{proc_id}}.pid"
exit_path = f"/tmp/suzent_proc_{{proc_id}}.exit"
with open(log_path, "wb", buffering=0) as log:
    p = subprocess.Popen({actual_cmd!r}, stdout=log, stderr=subprocess.STDOUT)
    open(pid_path, "w").write(str(p.pid))
    p.wait()
    open(exit_path, "w").write(str(p.returncode))
"""
        self._container.exec_run(
            ["python3", "-c", supervisor],
            workdir=Defaults.PERSISTENCE_MOUNT,
            detach=True,
        )
        return proc_id

    def poll_process(self, proc_id: str, offset: int = 0) -> dict:
        """Read new output from a background process since byte offset."""
        script = f"""
import os, json
log_path  = "/tmp/suzent_proc_{proc_id}.log"
exit_path = "/tmp/suzent_proc_{proc_id}.exit"
out = {{"output": "", "offset": {offset}, "done": False, "exit_code": None}}
if os.path.exists(log_path):
    with open(log_path, "rb") as f:
        f.seek({offset})
        data = f.read()
    out["output"] = data.decode("utf-8", errors="replace")
    out["offset"] = {offset} + len(data)
if os.path.exists(exit_path):
    out["exit_code"] = int(open(exit_path).read().strip())
    out["done"] = True
print(json.dumps(out))
"""
        exit_code, stdout, stderr = self._run_exec(
            ["python3", "-c", script], timeout=10
        )
        try:
            return json.loads(stdout.decode("utf-8", errors="replace"))
        except Exception:
            return {"output": "", "offset": offset, "done": False, "exit_code": None}

    def kill_process(self, proc_id: str) -> bool:
        """Send SIGTERM to a background process."""
        script = f"""
import os, signal
pid_path = "/tmp/suzent_proc_{proc_id}.pid"
if os.path.exists(pid_path):
    pid = int(open(pid_path).read().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print("killed")
    except ProcessLookupError:
        print("already_done")
else:
    print("not_found")
"""
        exit_code, stdout, _ = self._run_exec(["python3", "-c", script], timeout=10)
        return b"killed" in stdout or b"already_done" in stdout

    def _should_auto_heal(self, error_msg: str) -> bool:
        lower = error_msg.lower()
        return any(p in lower for p in Defaults.AUTO_HEAL_PATTERNS)

    def _run_exec(
        self,
        cmd: list,
        timeout: Optional[int] = None,
        environment: Optional[dict] = None,
    ) -> tuple:
        """
        Run a command in the container.
        Returns (exit_code, stdout_bytes, stderr_bytes).
        Raises TimeoutError or docker exceptions on failure.
        """
        effective_timeout = timeout or Defaults.EXEC_TIMEOUT
        result_holder: list = [None]
        exc_holder: list = [None]

        def _do():
            try:
                result_holder[0] = self._container.exec_run(
                    cmd,
                    workdir=Defaults.PERSISTENCE_MOUNT,
                    demux=True,
                    environment=environment or {},
                )
            except Exception as e:
                exc_holder[0] = e

        thread = threading.Thread(target=_do, daemon=True)
        thread.start()
        thread.join(effective_timeout)

        if thread.is_alive():
            # item 5: helpful timeout message
            raise TimeoutError(
                f"Execution timed out after {effective_timeout}s. "
                f"Retry with a higher timeout, e.g. timeout={effective_timeout * 2}."
            )

        if exc_holder[0]:
            raise exc_holder[0]

        res = result_holder[0]
        stdout, stderr = res.output if res.output else (None, None)
        return res.exit_code or 0, stdout or b"", stderr or b""

    def _execute_code(
        self, code: str, language: Language, timeout: Optional[int]
    ) -> ExecutionResult:
        """Execute Python or Node.js code via exec_run."""
        if language == Language.PYTHON:
            cmd = ["python3", "-c", code]
            env = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        else:
            cmd = ["node", "-e", code]
            env = {}

        exit_code, stdout, stderr = self._run_exec(cmd, timeout, environment=env)

        output = stdout.decode("utf-8", errors="replace").rstrip()
        error_output = stderr.decode("utf-8", errors="replace").rstrip()
        success = exit_code == 0

        return ExecutionResult(
            success=success,
            output=output,
            error=error_output if not success else None,
            exit_code=exit_code,
            language=language,
        )

    def _execute_command(self, content: str, timeout: Optional[int]) -> ExecutionResult:
        """Execute a shell command via bash."""
        cmd = ["bash", "-c", content]
        exit_code, stdout, stderr = self._run_exec(cmd, timeout)

        stdout_str = stdout.decode("utf-8", errors="replace").rstrip()
        stderr_str = stderr.decode("utf-8", errors="replace").rstrip()
        output = (stdout_str + "\n" + stderr_str).strip() if stderr_str else stdout_str
        success = exit_code == 0

        return ExecutionResult(
            success=success,
            output=output,
            error=stderr_str if not success else None,
            exit_code=exit_code,
            language=Language.COMMAND,
        )


# Backward compat alias
SandboxSession = DockerSession


# =============================================================================
# Sandbox Manager
# =============================================================================


class SandboxManager:
    """
    Manages Docker sandbox containers for multiple chat sessions.

    Each session gets its own named container. Containers are started on
    first use and stopped when the session ends. Host data persists
    regardless of container lifecycle.

    Usage:
        with SandboxManager() as manager:
            result = manager.execute("chat_id", "print('hello')")
    """

    def __init__(self, custom_volumes: Optional[List[str]] = None):
        import docker

        from suzent.config import CONFIG, get_effective_volumes

        self.data_path: str = getattr(CONFIG, "sandbox_data_path", "data/sandbox")
        self.image: str = getattr(CONFIG, "sandbox_image", Defaults.IMAGE)
        self.memory_mb: int = Defaults.MEMORY_MB
        self.cpus: int = Defaults.CPUS
        self.network: str = getattr(CONFIG, "sandbox_network", Defaults.NETWORK)
        self.idle_timeout: int = (
            getattr(CONFIG, "sandbox_idle_timeout_minutes", 30) * 60
        )
        self.setup_command: str = getattr(CONFIG, "sandbox_setup_command", "")
        self.env: Dict[str, str] = dict(getattr(CONFIG, "sandbox_env", {}) or {})
        self.custom_volumes: List[str] = get_effective_volumes(custom_volumes)

        self._client = docker.from_env()
        self._sessions: Dict[str, DockerSession] = {}
        self._stop_event = threading.Event()
        self._ensure_directories()
        self._cleanup_orphans()
        self._start_idle_cleanup_thread()

    def _ensure_directories(self) -> None:
        base = Path(self.data_path)
        (base / "shared").mkdir(parents=True, exist_ok=True)
        (base / "sessions").mkdir(parents=True, exist_ok=True)

    def _start_idle_cleanup_thread(self) -> None:
        """Start a daemon thread that periodically stops idle containers."""

        def _loop():
            while not self._stop_event.wait(Defaults.IDLE_CLEANUP_INTERVAL):
                try:
                    stopped = self.cleanup_idle_sessions()
                    if stopped:
                        logger.info(f"Idle cleanup: stopped {stopped} container(s)")
                except Exception as e:
                    logger.debug(f"Idle cleanup error: {e}")

        t = threading.Thread(target=_loop, daemon=True, name="sandbox-idle-cleanup")
        t.start()

    def _cleanup_orphans(self) -> None:
        """Remove suzent sandbox containers left over from previous app runs.
        Only runs once per process lifetime."""
        global _orphan_cleanup_done
        if _orphan_cleanup_done:
            return
        _orphan_cleanup_done = True
        try:
            containers = self._client.containers.list(
                all=True, filters={"label": "suzent.sandbox=true"}
            )
            for c in containers:
                try:
                    c.remove(force=True)
                    logger.info(f"Cleaned up orphan container: {c.name}")
                except Exception as e:
                    logger.debug(f"Could not clean orphan {c.name}: {e}")
        except Exception as e:
            logger.debug(f"Orphan cleanup failed: {e}")

    def __enter__(self) -> SandboxManager:
        return self

    def __exit__(self, *args) -> None:
        self.cleanup_all()

    def _create_session(self, session_id: str) -> DockerSession:
        return DockerSession(
            session_id=session_id,
            client=self._client,
            data_path=self.data_path,
            image=self.image,
            memory_mb=self.memory_mb,
            cpus=self.cpus,
            network=self.network,
            setup_command=self.setup_command,
            env=self.env,
            custom_volumes=self.custom_volumes,
        )

    def get_session(self, session_id: str) -> DockerSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = self._create_session(session_id)
        return self._sessions[session_id]

    def execute(
        self,
        session_id: str,
        content: str,
        language: Language | str = Language.PYTHON,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute code or command in a sandbox session."""
        if isinstance(language, str):
            try:
                language = Language(language.lower())
            except ValueError:
                return ExecutionResult.failure(f"Unknown language: {language}")
        return self.get_session(session_id).execute(content, language, timeout)

    def start_background(
        self,
        session_id: str,
        content: str,
        language: Language | str = Language.PYTHON,
    ) -> str:
        """Start a background process. Returns process_id."""
        if isinstance(language, str):
            language = Language(language.lower())
        return self.get_session(session_id).start_background(content, language)

    def poll_process(self, session_id: str, proc_id: str, offset: int = 0) -> dict:
        """Read new output from a background process."""
        return self.get_session(session_id).poll_process(proc_id, offset)

    def kill_process(self, session_id: str, proc_id: str) -> bool:
        """Kill a background process."""
        return self.get_session(session_id).kill_process(proc_id)

    def start_session(self, session_id: str) -> bool:
        """Explicitly pre-start a session container."""
        return self.get_session(session_id).start()

    def stop_session(self, session_id: str) -> bool:
        """Stop a session's container (data persists, can resume later)."""
        if session_id in self._sessions:
            result = self._sessions[session_id].stop()
            del self._sessions[session_id]
            return result
        return True

    def remove_session(self, session_id: str) -> bool:
        """Stop and remove a session's container (host data persists)."""
        if session_id in self._sessions:
            result = self._sessions[session_id].remove()
            del self._sessions[session_id]
            return result
        return True

    def cleanup_idle_sessions(self) -> int:
        """Stop containers idle longer than idle_timeout. Returns count stopped."""
        now = time.time()
        stopped = 0
        for session_id in list(self._sessions.keys()):
            session = self._sessions[session_id]
            if session.is_running and (now - session.last_used) > self.idle_timeout:
                logger.info(f"Stopping idle container for session {session_id}")
                session.stop()
                stopped += 1
        return stopped

    def cleanup_all(self) -> None:
        """Stop all active session containers and the idle cleanup thread."""
        self._stop_event.set()
        for session_id in list(self._sessions.keys()):
            self.stop_session(session_id)

    def is_available(self) -> bool:
        """Check if Docker daemon is reachable."""
        try:
            self._client.ping()
            return True
        except Exception:
            return False

    # Backward compat
    def is_server_available(self) -> bool:
        return self.is_available()

    @property
    def active_sessions(self) -> List[str]:
        return [sid for sid, s in self._sessions.items() if s.is_running]


# =============================================================================
# Utilities
# =============================================================================


def check_docker_available() -> bool:
    """Check if Docker daemon is running and accessible."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except Exception:
        return False


# Backward compat
def check_server_status(server_url: Optional[str] = None) -> bool:
    return check_docker_available()
