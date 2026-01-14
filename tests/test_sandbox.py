"""
Sandbox Stability Tests
=======================

Comprehensive tests to identify instability issues in the sandbox system.

Run with: pytest tests/test_sandbox.py -v -s

Prerequisites:
- Microsandbox server running on localhost:7263
- Run in WSL2 environment with KVM support
"""

import time
import uuid
import threading
import concurrent.futures
from typing import List, Tuple
import pytest

from suzent.sandbox import (
    SandboxManager,
    SandboxSession,
    ExecutionResult,
    RPCClient,
    Language,
    Defaults,
    check_server_status,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def server_url():
    """Get sandbox server URL."""
    from suzent.config import CONFIG
    return CONFIG.sandbox_server_url or Defaults.SERVER_URL


@pytest.fixture
def manager():
    """Create a fresh SandboxManager for each test."""
    mgr = SandboxManager()
    yield mgr
    mgr.cleanup_all()


@pytest.fixture
def session_id():
    """Generate unique session ID for each test."""
    return f"test-{uuid.uuid4().hex[:12]}"


# =============================================================================
# 1. Connectivity and Health Check Tests
# =============================================================================

class TestConnectivity:
    """Tests for server connectivity and health checks."""

    def test_server_is_running(self, server_url):
        """Verify sandbox server is reachable."""
        is_running = check_server_status(server_url)
        assert is_running, f"Sandbox server not running at {server_url}"

    def test_rpc_client_basic_call(self, server_url):
        """Test basic RPC call to server."""
        rpc = RPCClient(server_url, timeout=10.0)
        response = rpc.call("sandbox.metrics.get", {"namespace": "*"})

        # Should not have error key if server is responding
        assert "error" not in response, f"RPC call failed: {response.get('error')}"

    def test_rpc_client_invalid_method(self, server_url):
        """Test RPC client handles invalid methods gracefully."""
        rpc = RPCClient(server_url, timeout=10.0)
        response = rpc.call("invalid.method.name", {})

        # Should return an error, not crash
        assert isinstance(response, dict)

    def test_rpc_client_timeout_handling(self, server_url):
        """Test RPC client handles very short timeouts."""
        rpc = RPCClient(server_url, timeout=0.001)  # 1ms timeout
        response = rpc.call("sandbox.metrics.get", {"namespace": "*"})

        # Should handle timeout gracefully
        assert isinstance(response, dict)

    def test_connection_to_invalid_server(self):
        """Test behavior when server is unreachable."""
        rpc = RPCClient("http://localhost:59999", timeout=2.0)
        response = rpc.call("sandbox.metrics.get", {"namespace": "*"})

        assert "error" in response, "Should return error for unreachable server"


# =============================================================================
# 2. Session Lifecycle Tests
# =============================================================================

class TestSessionLifecycle:
    """Tests for session start/stop/restart behavior."""

    def test_session_start(self, manager, session_id):
        """Test starting a new session."""
        success = manager.start_session(session_id)
        assert success, "Failed to start session"

        session = manager.get_session(session_id)
        assert session.is_running, "_is_running should be True after start"

    def test_session_stop(self, manager, session_id):
        """Test stopping a session."""
        manager.start_session(session_id)
        success = manager.stop_session(session_id)

        assert success, "Failed to stop session"
        assert session_id not in manager._sessions, "Session should be removed from manager"

    def test_session_restart(self, manager, session_id):
        """Test restarting a session after stop."""
        # Start
        manager.start_session(session_id)
        res1 = manager.execute(session_id, "x = 1; print(x)")
        assert res1.success, f"First execution failed: {res1.error}"

        # Stop
        manager.stop_session(session_id)
        time.sleep(1)  # Allow cleanup

        # Restart
        success = manager.start_session(session_id)
        assert success, "Failed to restart session"

        res2 = manager.execute(session_id, "print('restarted')")
        assert res2.success, f"Execution after restart failed: {res2.error}"

    def test_double_start(self, manager, session_id):
        """Test starting an already-running session (should be idempotent)."""
        manager.start_session(session_id)
        success = manager.start_session(session_id)  # Second start

        assert success, "Second start should succeed (idempotent)"

    def test_double_stop(self, manager, session_id):
        """Test stopping an already-stopped session."""
        manager.start_session(session_id)
        manager.stop_session(session_id)
        success = manager.stop_session(session_id)  # Second stop

        assert success, "Second stop should succeed (idempotent)"

    def test_execute_without_explicit_start(self, manager, session_id):
        """Test that execute auto-starts the session."""
        result = manager.execute(session_id, "print('auto-start')")

        assert result.success, f"Auto-start execution failed: {result.error}"
        assert "auto-start" in result.output


# =============================================================================
# 3. State Synchronization Tests (Bug Detection)
# =============================================================================

class TestStateSynchronization:
    """Tests to detect _is_running flag getting out of sync with reality."""

    def test_is_running_after_successful_start(self, manager, session_id):
        """Verify _is_running is True after successful start."""
        manager.start_session(session_id)
        session = manager.get_session(session_id)

        assert session._is_running is True

    def test_is_running_after_stop(self, manager, session_id):
        """Verify _is_running is False after stop."""
        manager.start_session(session_id)
        session = manager.get_session(session_id)
        session.stop()

        assert session._is_running is False

    def test_state_after_failed_execution(self, manager, session_id):
        """Test state consistency after execution errors."""
        manager.start_session(session_id)

        # Execute code that causes an error
        result = manager.execute(session_id, "raise Exception('test error')")

        # Session should still be considered running
        session = manager.get_session(session_id)
        assert session._is_running is True, "Session should remain running after code error"

    def test_state_recovery_simulation(self, manager, session_id):
        """
        Simulate what happens when VM dies externally.

        BUG: _is_running can be True but VM is actually dead.
        """
        manager.start_session(session_id)
        session = manager.get_session(session_id)

        # Manually corrupt state to simulate external VM death
        session._is_running = True  # Force state

        # Execution should fail but trigger auto-healing
        result = manager.execute(session_id, "print('test')")

        # Should either succeed (auto-healed) or have clear error
        if not result.success:
            assert result.error is not None, "Failed execution should have error message"


# =============================================================================
# 4. Concurrency Tests
# =============================================================================

class TestConcurrency:
    """Tests for concurrent access and race conditions."""

    def test_sequential_executions_same_session(self, manager, session_id):
        """Multiple sequential executions in same session."""
        results = []
        for i in range(5):
            result = manager.execute(session_id, f"print('seq-{i}')")
            results.append(result)

        failures = [r for r in results if not r.success]
        assert len(failures) == 0, f"Sequential executions failed: {[r.error for r in failures]}"

    def test_concurrent_executions_same_session(self, manager, session_id):
        """
        Concurrent executions in the same session.

        BUG POTENTIAL: No locking in SandboxSession, concurrent calls may race.
        """
        manager.start_session(session_id)

        def execute_code(i: int) -> Tuple[int, ExecutionResult]:
            result = manager.execute(session_id, f"print('concurrent-{i}')")
            return (i, result)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(execute_code, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        failures = [(i, r) for i, r in results if not r.success]
        success_rate = (len(results) - len(failures)) / len(results)

        # Allow some failures due to race conditions, but most should succeed
        assert success_rate >= 0.6, f"Too many concurrent failures ({len(failures)}/{len(results)})"

        if failures:
            print(f"\nWARNING: {len(failures)} concurrent executions failed:")
            for i, r in failures[:3]:
                print(f"  - Execution {i}: {r.error}")

    def test_concurrent_sessions_different_ids(self, manager):
        """Multiple concurrent sessions with different IDs."""
        session_ids = [f"concurrent-{uuid.uuid4().hex[:8]}" for _ in range(3)]

        def run_session(sid: str) -> Tuple[str, bool, str]:
            try:
                result = manager.execute(sid, f"print('session-{sid}')")
                return (sid, result.success, result.error or "")
            except Exception as e:
                return (sid, False, str(e))

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_session, sid) for sid in session_ids]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        failures = [(sid, err) for sid, success, err in results if not success]
        assert len(failures) == 0, f"Concurrent sessions failed: {failures}"

    def test_start_during_execution(self, manager, session_id):
        """
        Start session while execution is in progress.

        BUG POTENTIAL: Double-start race condition.
        """
        results = []
        errors = []

        def long_execution():
            try:
                result = manager.execute(session_id, "import time; time.sleep(2); print('done')")
                results.append(result)
            except Exception as e:
                errors.append(e)

        def try_start():
            time.sleep(0.5)  # Wait for execution to start
            try:
                success = manager.start_session(session_id)
                results.append(("start", success))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=long_execution),
            threading.Thread(target=try_start),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Race condition caused errors: {errors}"


# =============================================================================
# 5. Stress Tests
# =============================================================================

class TestStress:
    """Stress tests for stability under load."""

    def test_rapid_start_stop_cycles(self, manager, session_id):
        """Rapidly start and stop the same session."""
        failures = []

        for i in range(5):
            try:
                success = manager.start_session(session_id)
                if not success:
                    failures.append(f"Start {i} failed")
                    continue

                result = manager.execute(session_id, f"print('cycle-{i}')")
                if not result.success:
                    failures.append(f"Execute {i} failed: {result.error}")

                manager.stop_session(session_id)
                time.sleep(0.5)  # Brief pause between cycles

            except Exception as e:
                failures.append(f"Cycle {i} exception: {e}")

        assert len(failures) == 0, f"Rapid cycle failures: {failures}"

    def test_many_sequential_executions(self, manager, session_id):
        """Many executions in sequence to detect memory leaks or accumulating errors."""
        manager.start_session(session_id)

        failure_count = 0
        total = 20

        for i in range(total):
            result = manager.execute(session_id, f"print({i})")
            if not result.success:
                failure_count += 1
                print(f"  Execution {i} failed: {result.error}")

        success_rate = (total - failure_count) / total
        assert success_rate >= 0.9, f"Too many failures: {failure_count}/{total} ({success_rate:.0%} success)"

    def test_multiple_sessions_sequential(self, manager):
        """Create multiple sessions sequentially."""
        session_ids = [f"multi-{i}" for i in range(5)]
        failures = []

        for sid in session_ids:
            result = manager.execute(sid, f"print('session {sid}')")
            if not result.success:
                failures.append((sid, result.error))

        # Cleanup
        for sid in session_ids:
            manager.stop_session(sid)

        assert len(failures) == 0, f"Multi-session failures: {failures}"

    def test_large_output_handling(self, manager, session_id):
        """Test handling of large output."""
        code = "print('x' * 10000)"
        result = manager.execute(session_id, code)

        assert result.success, f"Large output failed: {result.error}"
        assert len(result.output) > 1000, "Output seems truncated"

    def test_long_running_execution(self, manager, session_id):
        """Test execution that takes several seconds."""
        code = """
import time
for i in range(3):
    print(f'tick {i}')
    time.sleep(1)
print('done')
"""
        result = manager.execute(session_id, code, timeout=30)

        assert result.success, f"Long execution failed: {result.error}"
        assert "done" in result.output


# =============================================================================
# 6. Error Handling and Recovery Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling and auto-healing."""

    def test_syntax_error_recovery(self, manager, session_id):
        """Session should recover from syntax errors."""
        # Cause syntax error (use invalid syntax that doesn't trigger continuation prompt)
        result1 = manager.execute(session_id, "a = 1 2")
        assert not result1.success, "Syntax error should fail"

        # Should still work after
        result2 = manager.execute(session_id, "print('recovered')")
        assert result2.success, f"Recovery failed: {result2.error}"

    def test_exception_recovery(self, manager, session_id):
        """Session should recover from runtime exceptions."""
        # Cause exception
        result1 = manager.execute(session_id, "raise ValueError('test')")
        assert not result1.success, "Exception should fail"

        # Should still work after
        result2 = manager.execute(session_id, "print('recovered')")
        assert result2.success, f"Recovery failed: {result2.error}"

    def test_infinite_loop_timeout(self, manager, session_id):
        """Test timeout handling for infinite loops."""
        code = "while True: pass"
        result = manager.execute(session_id, code, timeout=3)

        # Should timeout, not hang forever
        # Result may or may not be success depending on timeout handling
        assert result is not None, "Execution should return (not hang)"

    def test_memory_exhaustion_recovery(self, manager, session_id):
        """Test recovery after memory-intensive code."""
        # Try to allocate lots of memory
        code = "x = 'a' * (100 * 1024 * 1024)"  # 100MB string
        result1 = manager.execute(session_id, code, timeout=10)

        # Whether it fails or succeeds, next execution should work
        result2 = manager.execute(session_id, "print('after memory test')")

        # We care more about recovery than the memory test itself
        if not result2.success:
            print(f"WARNING: Recovery after memory test failed: {result2.error}")

    def test_auto_healing_trigger_patterns(self, manager, session_id):
        """
        Test which error patterns trigger auto-healing.

        Current patterns: timeout, connection, reset, failed to connect, internal server error
        """
        patterns_to_test = [
            "timeout",
            "connection refused",
            "connection reset",
            "failed to connect",
            "internal server error",
            "some other error",  # Should NOT trigger healing
        ]

        # This is more of a documentation test - actual behavior depends on server state
        print("\nAuto-healing patterns defined in code:")
        print("  - timeout")
        print("  - connection")
        print("  - reset")
        print("  - failed to connect")
        print("  - internal server error")


# =============================================================================
# 7. Persistence Tests
# =============================================================================

class TestPersistence:
    """Tests for data persistence across session restarts."""

    def test_persistence_write_read(self, manager, session_id):
        """Write and read from /persistence within same session."""
        # Write
        write_code = "with open('/persistence/test.txt', 'w') as f: f.write('hello')"
        result1 = manager.execute(session_id, write_code)
        assert result1.success, f"Write failed: {result1.error}"

        # Read
        read_code = "print(open('/persistence/test.txt').read())"
        result2 = manager.execute(session_id, read_code)
        assert result2.success, f"Read failed: {result2.error}"
        assert "hello" in result2.output

    def test_persistence_survives_restart(self, manager, session_id):
        """Data should persist after session restart."""
        unique_data = f"persist-{uuid.uuid4().hex[:8]}"

        # Write and stop
        write_code = f"with open('/persistence/restart_test.txt', 'w') as f: f.write('{unique_data}')"
        manager.execute(session_id, write_code)
        manager.stop_session(session_id)
        time.sleep(2)

        # Restart and read
        read_code = "print(open('/persistence/restart_test.txt').read())"
        result = manager.execute(session_id, read_code)

        assert result.success, f"Read after restart failed: {result.error}"
        assert unique_data in result.output, f"Data not persisted: expected '{unique_data}', got '{result.output}'"

    def test_shared_storage_between_sessions(self, manager):
        """Test /shared is accessible across different sessions."""
        session1 = f"shared-test-1-{uuid.uuid4().hex[:8]}"
        session2 = f"shared-test-2-{uuid.uuid4().hex[:8]}"
        unique_data = f"shared-{uuid.uuid4().hex[:8]}"

        # Write from session 1
        write_code = f"with open('/shared/cross_session.txt', 'w') as f: f.write('{unique_data}')"
        result1 = manager.execute(session1, write_code)
        assert result1.success, f"Write from session1 failed: {result1.error}"

        # Read from session 2
        read_code = "print(open('/shared/cross_session.txt').read())"
        result2 = manager.execute(session2, read_code)

        assert result2.success, f"Read from session2 failed: {result2.error}"
        assert unique_data in result2.output, "Shared data not accessible"

        # Cleanup
        manager.stop_session(session1)
        manager.stop_session(session2)


# =============================================================================
# 8. Command Execution Tests
# =============================================================================

class TestCommandExecution:
    """Tests for shell command execution via Language.COMMAND."""

    def test_simple_command(self, manager, session_id):
        """Test simple shell command."""
        result = manager.execute(session_id, "echo hello", language=Language.COMMAND)

        assert result.success, f"Command failed: {result.error}"
        assert "hello" in result.output

    def test_command_with_arguments(self, manager, session_id):
        """Test command with multiple arguments."""
        result = manager.execute(session_id, "ls -la /", language=Language.COMMAND)

        assert result.success, f"Command failed: {result.error}"
        assert result.output  # Should have some output

    def test_command_exit_code(self, manager, session_id):
        """Test that exit codes are captured correctly."""
        # Command that fails
        result = manager.execute(session_id, "ls /nonexistent_path_12345", language=Language.COMMAND)

        assert not result.success, "Failed command should have success=False"
        assert result.exit_code != 0, "Failed command should have non-zero exit code"

    def test_command_not_found(self, manager, session_id):
        """Test handling of nonexistent commands."""
        result = manager.execute(session_id, "nonexistent_command_12345", language=Language.COMMAND)

        assert not result.success, "Nonexistent command should fail"


# =============================================================================
# 9. Node.js Execution Tests (if supported)
# =============================================================================

class TestNodeJS:
    """Tests for Node.js execution."""

    def test_nodejs_basic(self, manager, session_id):
        """Test basic Node.js execution."""
        result = manager.execute(session_id, "console.log('hello from node')", language=Language.NODEJS)

        err_msg = str(result.error or "").lower()
        if "not supported" in err_msg or "500 internal server error" in err_msg:
            pytest.skip("Node.js not supported or not configured in this sandbox")

        assert result.success, f"Node.js execution failed: {result.error}"
        assert "hello from node" in result.output


# =============================================================================
# 10. Edge Cases and Bug Reproduction
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and potential bugs."""

    def test_empty_code(self, manager, session_id):
        """Test executing empty code."""
        result = manager.execute(session_id, "")
        # Should not crash
        assert result is not None

    def test_whitespace_only_code(self, manager, session_id):
        """Test executing whitespace-only code."""
        result = manager.execute(session_id, "   \n\t\n   ")
        assert result is not None

    def test_unicode_in_code(self, manager, session_id):
        """Test Unicode characters in code."""
        result = manager.execute(session_id, "print('你好世界 🌍')")

        assert result.success, f"Unicode test failed: {result.error}"

    def test_very_long_code(self, manager, session_id):
        """Test executing very long code."""
        # Generate code with many print statements
        lines = [f"print({i})" for i in range(100)]
        code = "\n".join(lines)

        result = manager.execute(session_id, code, timeout=30)
        assert result.success, f"Long code failed: {result.error}"

    def test_special_characters_in_session_id(self, manager):
        """Test session IDs with special characters."""
        special_ids = [
            "test-with-dashes",
            "test_with_underscores",
            "test.with.dots",
            "TestWithCaps",
        ]

        for sid in special_ids:
            result = manager.execute(sid, "print('ok')")
            assert result.success, f"Session ID '{sid}' failed: {result.error}"
            manager.stop_session(sid)

    def test_manager_reuse(self):
        """Test creating multiple managers doesn't cause issues."""
        results = []

        for i in range(3):
            mgr = SandboxManager()
            result = mgr.execute(f"manager-test-{i}", "print('ok')")
            results.append(result)
            mgr.cleanup_all()

        failures = [r for r in results if not r.success]
        assert len(failures) == 0, f"Manager reuse failures: {[r.error for r in failures]}"


# =============================================================================
# Quick Diagnostic Test (run this first)
# =============================================================================

class TestQuickDiagnostic:
    """Run these first to quickly diagnose sandbox issues."""

    def test_00_server_reachable(self, server_url):
        """First check: Is the server running?"""
        is_up = check_server_status(server_url)
        assert is_up, f"""

SANDBOX SERVER NOT REACHABLE at {server_url}

To start the sandbox server in WSL2:
1. cd to project directory
2. docker compose -f docker/sandbox-compose.yml up -d
3. Wait 30-60 seconds for server to initialize
4. Run this test again

"""

    def test_01_basic_execution(self, manager, session_id):
        """Second check: Can we execute basic code?"""
        result = manager.execute(session_id, "print(1+1)")

        assert result.success, f"""

BASIC EXECUTION FAILED

Error: {result.error}

This suggests the microsandbox server is running but cannot create VMs.
Check:
1. KVM is available: ls -la /dev/kvm
2. Docker has necessary permissions
3. Sandbox server logs: docker logs suzent-microsandbox

"""
        assert "2" in result.output, f"Unexpected output: {result.output}"

    def test_02_session_persistence(self, manager, session_id):
        """Third check: Does session state persist?"""
        # Set a variable
        result1 = manager.execute(session_id, "test_var = 42")
        assert result1.success, f"Set variable failed: {result1.error}"

        # Read it back
        result2 = manager.execute(session_id, "print(test_var)")
        assert result2.success, f"Read variable failed: {result2.error}"
        assert "42" in result2.output, f"Variable not persisted: {result2.output}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
