"""
Tests for device discovery (Tailscale peer parsing, reachability probe) and
the outbound connection manager.
"""

import asyncio
import json

import pytest

from suzent.nodes import discovery
from suzent.nodes.outbound import OutboundConnectionManager


# ─── Tailscale peer parsing ──────────────────────────────────────────


_TS_STATUS = {
    "Peer": {
        "n1": {
            "HostName": "laptop",
            "DNSName": "laptop.tail123.ts.net.",
            "TailscaleIPs": ["100.64.0.5", "fd7a::5"],
            "Online": True,
        },
        "n2": {
            "HostName": "offline-box",
            "DNSName": "offline.tail123.ts.net.",
            "TailscaleIPs": ["100.64.0.6"],
            "Online": False,
        },
        "n3": {
            "HostName": "no-ip",
            "DNSName": "",
            "TailscaleIPs": [],
            "Online": True,
        },
    }
}


class TestTailscaleParsing:
    def test_parses_online_peers_only(self, monkeypatch):
        def fake_run(cmd, capture_output, text, timeout):
            class R:
                stdout = json.dumps(_TS_STATUS)

            return R()

        monkeypatch.setattr(discovery, "_tailscale_exe", lambda: "/usr/bin/tailscale")
        monkeypatch.setattr(discovery.subprocess, "run", fake_run)

        peers = discovery._tailscale_peers_blocking(25314)
        # Only the online peer with an address survives.
        assert len(peers) == 1
        p = peers[0]
        assert p["source"] == "tailscale"
        assert p["dns_name"] == "laptop.tail123.ts.net"  # trailing dot stripped
        assert p["tailscale_ip"] == "100.64.0.5"
        # Prefer the 100.x IP for the URL (works without MagicDNS).
        assert p["gateway_url"] == "ws://100.64.0.5:25314/ws/node"

    def test_no_tailscale_binary(self, monkeypatch):
        monkeypatch.setattr(discovery, "_tailscale_exe", lambda: None)
        assert discovery._tailscale_peers_blocking(25314) == []


# ─── Reachability probe ──────────────────────────────────────────────


class TestProbe:
    @pytest.mark.asyncio
    async def test_probe_open_port(self):
        import socket

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            assert await discovery.probe_reachable("127.0.0.1", port, timeout=1.0)
        finally:
            sock.close()

    @pytest.mark.asyncio
    async def test_probe_closed_port(self):
        # Unassigned port — connection should fail fast.
        assert not await discovery.probe_reachable("127.0.0.1", 1, timeout=0.5)


# ─── Outbound connection manager ─────────────────────────────────────


class TestOutboundManager:
    @pytest.mark.asyncio
    async def test_start_list_stop(self, monkeypatch):
        # Avoid a real websocket: stub NodeHost.run to idle until stopped.
        from suzent.nodes import outbound

        started = {}

        class FakeHost:
            def __init__(self, gateway_url, display_name):
                self.gateway_url = gateway_url
                self.display_name = display_name
                self.status = "connecting"
                self.pairing_code = None
                self.node_id = None
                self.last_error = None
                self._stop = False
                started["url"] = gateway_url

            async def run(self):
                while not self._stop:
                    await asyncio.sleep(0.01)

            def stop(self):
                self._stop = True
                self.status = "stopped"

        monkeypatch.setattr(outbound, "NodeHost", FakeHost)
        mgr = OutboundConnectionManager()

        host = mgr.start("ws://peer:25314/ws/node", display_name="Me")
        assert host.display_name == "Me"
        assert started["url"] == "ws://peer:25314/ws/node"

        listed = mgr.list()
        assert len(listed) == 1
        assert listed[0]["gateway_url"] == "ws://peer:25314/ws/node"

        # Starting the same gateway again returns the existing connection.
        again = mgr.start("ws://peer:25314/ws/node")
        assert again is host

        assert await mgr.stop("ws://peer:25314/ws/node") is True
        assert mgr.list() == []
        assert await mgr.stop("ws://peer:25314/ws/node") is False
