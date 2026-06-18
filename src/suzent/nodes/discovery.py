"""
Device discovery for the node mesh.

Two independent mechanisms — they do NOT overlap:

* **LAN (mDNS / Bonjour)** — advertise a ``_suzent-node._tcp`` service and
  browse for peers on the local link. Finds same-subnet machines only;
  multicast does not traverse a Tailscale overlay.
* **Tailscale** — enumerate online tailnet peers via the local ``tailscale``
  CLI. Works across networks; needs Tailscale installed and up.

Discovery only *locates* candidate gateways — it never bypasses
``node_auth_mode``. Approval/token still gate the actual connection.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess

from suzent.logger import get_logger

logger = get_logger(__name__)

SERVICE_TYPE = "_suzent-node._tcp.local."


def _local_ip() -> str:
    """Best-effort primary LAN IP (the default-route interface)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


# ─── mDNS advertising ────────────────────────────────────────────────


class SuzentAdvertiser:
    """Advertises this server as a ``_suzent-node._tcp`` mDNS service.

    Best-effort and import-safe: if zeroconf is unavailable or registration
    fails, it logs and stays silent rather than breaking server startup.
    """

    def __init__(self, port: int, display_name: str, auth_mode: str = "open"):
        self.port = port
        self.display_name = display_name
        self.auth_mode = auth_mode
        self._zc = None
        self._info = None

    def start(self) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf

            ip = _local_ip()
            safe_name = self.display_name.replace(".", "-")
            self._info = ServiceInfo(
                SERVICE_TYPE,
                f"{safe_name}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(ip)],
                port=self.port,
                properties={
                    "display_name": self.display_name,
                    "auth_mode": self.auth_mode,
                    "path": "/ws/node",
                },
                server=f"{socket.gethostname()}.local.",
            )
            self._zc = Zeroconf()
            self._zc.register_service(self._info)
            logger.info(
                f"mDNS: advertising '{self.display_name}' as {SERVICE_TYPE} "
                f"on {ip}:{self.port}"
            )
        except Exception as e:
            logger.warning(f"mDNS advertising disabled: {e}")
            self._zc = None

    def stop(self) -> None:
        try:
            if self._zc and self._info:
                self._zc.unregister_service(self._info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass
        finally:
            self._zc = None


# ─── mDNS browsing ───────────────────────────────────────────────────


def _browse_lan_blocking(timeout: float, self_port: int) -> list[dict]:
    """Synchronously browse for peers (run in a thread)."""
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except Exception as e:
        logger.warning(f"mDNS browse unavailable: {e}")
        return []

    found: dict[str, dict] = {}
    self_ip = _local_ip()

    class _Listener(ServiceListener):
        def _record(self, zc, type_, name):
            try:
                info = zc.get_service_info(type_, name, timeout=int(timeout * 1000))
                if not info or not info.addresses:
                    return
                host = socket.inet_ntoa(info.addresses[0])
                # Skip our own advertisement.
                if host == self_ip and info.port == self_port:
                    return
                props = {
                    k.decode(): (v.decode() if isinstance(v, bytes) else v)
                    for k, v in (info.properties or {}).items()
                }
                found[name] = {
                    "name": props.get("display_name", name.split(".")[0]),
                    "host": host,
                    "port": info.port,
                    "auth_mode": props.get("auth_mode", "unknown"),
                    "gateway_url": f"ws://{host}:{info.port}/ws/node",
                    "source": "lan",
                }
            except Exception:
                pass

        def add_service(self, zc, type_, name):
            self._record(zc, type_, name)

        def update_service(self, zc, type_, name):
            self._record(zc, type_, name)

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, SERVICE_TYPE, _Listener())
        import time

        time.sleep(timeout)
    finally:
        zc.close()
    return list(found.values())


async def browse_lan(timeout: float = 2.0, self_port: int = 0) -> list[dict]:
    """Browse the local network for Suzent node services via mDNS."""
    return await asyncio.to_thread(_browse_lan_blocking, timeout, self_port)


# ─── Tailscale peers ─────────────────────────────────────────────────


def _tailscale_exe() -> str | None:
    exe = shutil.which("tailscale")
    if exe:
        return exe
    mac_path = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    return mac_path if os.path.exists(mac_path) else None


def _tailscale_peers_blocking(port: int) -> list[dict]:
    exe = _tailscale_exe()
    if not exe:
        return []
    try:
        res = subprocess.run(
            [exe, "status", "--json"], capture_output=True, text=True, timeout=3
        )
        data = json.loads(res.stdout or "{}")
    except Exception as e:
        logger.warning(f"Tailscale peer enumeration failed: {e}")
        return []

    peers = []
    for peer in (data.get("Peer", {}) or {}).values():
        if not peer.get("Online"):
            continue
        ips = peer.get("TailscaleIPs", []) or []
        host = next((ip for ip in ips if ip.startswith("100.")), ips[0] if ips else "")
        dns = (peer.get("DNSName", "") or "").rstrip(".")
        if not host and not dns:
            continue
        addr = dns or host
        peers.append(
            {
                "name": (peer.get("HostName") or dns or host),
                "host": addr,
                "port": port,
                "tailscale_ip": host,
                "dns_name": dns,
                "gateway_url": f"ws://{addr}:{port}/ws/node",
                "source": "tailscale",
            }
        )
    return peers


async def tailscale_peers(port: int) -> list[dict]:
    """List online tailnet peers as candidate gateways."""
    return await asyncio.to_thread(_tailscale_peers_blocking, port)


# ─── Reachability probe ──────────────────────────────────────────────


async def probe_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP connect to see if a candidate is actually listening."""
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def _annotate_reachable(candidates: list[dict], timeout: float = 1.0) -> None:
    """Set ``reachable`` on each candidate by probing its port in parallel."""

    async def _one(c):
        c["reachable"] = await probe_reachable(c["host"], c["port"], timeout)

    await asyncio.gather(*(_one(c) for c in candidates), return_exceptions=True)


async def discover_all(
    self_port: int, lan_timeout: float = 2.0, probe: bool = True
) -> dict:
    """Run LAN + Tailscale discovery concurrently and probe reachability."""
    lan, ts = await asyncio.gather(
        browse_lan(lan_timeout, self_port),
        tailscale_peers(self_port),
    )
    if probe:
        await asyncio.gather(_annotate_reachable(lan), _annotate_reachable(ts))
    return {"lan": lan, "tailscale": ts}
