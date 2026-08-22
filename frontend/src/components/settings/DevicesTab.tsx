import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ComputerDesktopIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline';

import {
  fetchNodes,
  fetchPendingNodes,
  fetchApprovedDevices,
  fetchUnauthorizedTriggers,
  fetchNodeConfig,
  approvePendingNode,
  denyPendingNode,
  revokeDevice,
  setDeviceStatus,
  discoverNodes,
  fetchConnections,
  fetchGrants,
  approveGrant,
  denyGrant,
  fetchPeers,
  setPeerReverse,
  removePeer,
  requestControl,
  controlStatus,
  type ConnectedNode,
  type NodeCapabilityInfo,
  type PendingNode,
  type ApprovedDevice,
  type NodeAuthConfig,
  type DiscoveredPeer,
  type OutboundConnection,
  type ControlRequest,
  type ControlledPeer,
  type UnauthorizedTrigger,
} from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalButton } from '../BrutalButton';
import { BrutalOnOff } from '../BrutalOnOff';
import { SettingsHeader } from './SettingsHeader';
import { NodeInvokePanel, PeerInvokePanel } from './NodeInvokePanel';
import { CopyButton } from './CopyButton';
import { BrowserNodeQR } from './BrowserNodeQR';
import { NetworkAccessStrip } from './NetworkAccessCard';
import { PeerTriggerPanel } from './PeerTriggerPanel';
import { SectionCardHeader, SettingsCard, SettingsListItem, SettingsListAction, SettingsPage } from './SettingsCard';
import { relativeTime } from '../../lib/chatUtils';

const POLL_MS = 4000;
const AGENT_CAPABILITY = 'agent.run';

function capNames(caps: { name: string }[]): string {
  return caps.length ? caps.map((c) => c.name).join(', ') : 'none';
}

function isAgent(node: { capabilities: { name: string }[] }): boolean {
  return node.capabilities.some((c) => c.name === AGENT_CAPABILITY);
}

/** Read-only status pill (used for the outbound direction and empty states). */
function StatusPill({ tone, label }: { tone: 'green' | 'neutral' | 'red'; label: string }): React.ReactElement {
  if (tone === 'neutral') {
    return (
      <span className="inline-flex min-w-14 items-center justify-center border border-neutral-300 dark:border-white/10 bg-white/70 dark:bg-zinc-900 px-2 py-1 text-[10px] font-black uppercase text-neutral-400 dark:text-neutral-500">
        {label}
      </span>
    );
  }
  const cls = tone === 'red'
    ? 'border-brutal-red bg-red-50 text-brutal-red dark:bg-red-950/40'
    : 'border-brutal-black bg-brutal-green text-brutal-black';
  return (
    <span className={`inline-flex min-w-16 items-center justify-center border-2 px-2 py-1 text-[10px] font-black uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  );
}

/** A compact on/off toggle for a direction the user owns (inbound grants). */
function DirectionToggle({ on, busy, onToggle }: { on: boolean; busy: boolean; onToggle: () => void }): React.ReactElement {
  return (
    <button
      role="switch"
      aria-checked={on}
      disabled={busy}
      onClick={onToggle}
      className={`inline-flex min-w-24 items-center justify-center gap-1.5 border-2 px-2.5 py-1 text-[10px] font-black uppercase tracking-wide shadow-brutal-sm transition-all active:translate-x-[1px] active:translate-y-[1px] active:shadow-none disabled:opacity-40 ${
        on
          ? 'border-brutal-black bg-brutal-green text-brutal-black hover:brightness-105'
          : 'border-brutal-black bg-white text-neutral-500 hover:bg-neutral-100 dark:bg-zinc-900 dark:text-neutral-300 dark:hover:bg-zinc-800'
      }`}
    >
      <span className={`h-2 w-2 border border-brutal-black ${on ? 'bg-brutal-black' : 'bg-transparent dark:border-white'}`} />
      {on ? 'Granted' : 'Off'}
    </button>
  );
}

export function DevicesTab(): React.ReactElement {
  const [nodes, setNodes] = useState<ConnectedNode[]>([]);
  const [pending, setPending] = useState<PendingNode[]>([]);
  const [devices, setDevices] = useState<ApprovedDevice[]>([]);
  const [config, setConfig] = useState<NodeAuthConfig | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [addrHost, setAddrHost] = useState<string | null>(null);
  const [connections, setConnections] = useState<OutboundConnection[]>([]);
  const [grants, setGrants] = useState<ControlRequest[]>([]);
  const [peers, setPeers] = useState<ControlledPeer[]>([]);
  const [discovered, setDiscovered] = useState<{ lan: DiscoveredPeer[]; tailscale: DiscoveredPeer[] } | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [showScreenPairing, setShowScreenPairing] = useState(false);
  const [unauthorized, setUnauthorized] = useState<UnauthorizedTrigger[]>([]);
  // Outstanding control requests awaiting the remote operator's approval,
  // keyed by base_url → { request_id, name }. The regular refresh() reconciles
  // these so a late approval still finalizes (the requester's poll gives up
  // after a few minutes, but the grant lives longer on the target).
  const outstanding = useRef<Map<string, { requestId: string; name: string }>>(new Map());

  const refresh = useCallback(async () => {
    // Finalize any outstanding control requests whose approval has landed.
    if (outstanding.current.size) {
      await Promise.all(
        [...outstanding.current.entries()].map(async ([baseUrl, { requestId, name }]) => {
          try {
            const s = await controlStatus(baseUrl, requestId, name);
            if (s.status === 'approved' || s.status === 'denied' || s.status === 'expired') {
              outstanding.current.delete(baseUrl);
              if (s.status !== 'approved') setError(`Control request ${s.status}.`);
            }
          } catch {
            // Peer unreachable this tick — keep trying on later refreshes.
          }
        })
      );
    }
    const [n, p, d, c, g, pe, ua] = await Promise.all([
      fetchNodes(),
      fetchPendingNodes(),
      fetchApprovedDevices(),
      fetchConnections(),
      fetchGrants(),
      fetchPeers(),
      fetchUnauthorizedTriggers(),
    ]);
    setNodes(n);
    setPending(p);
    setDevices(d);
    setConnections(c);
    setGrants(g);
    setPeers(pe);
    setUnauthorized(ua);
  }, []);

  // Connect = "I want to control this device": request a grant, then let the
  // regular refresh loop finalize it whenever the operator approves (works for
  // the whole grant window, not just a short foreground poll).
  const handleControl = useCallback(
    async (baseUrl: string, name = '') => {
      setBusy(baseUrl);
      setError(null);
      try {
        const { request_id, base_url } = await requestControl(baseUrl);
        outstanding.current.set(base_url, { requestId: request_id, name });
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(null);
      }
    },
    [refresh]
  );

  const runDiscover = useCallback(async () => {
    setDiscovering(true);
    setError(null);
    try {
      setDiscovered(await discoverNodes(2.0));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDiscovering(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    fetchNodeConfig().then(setConfig).catch(() => {});
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const act = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  // Fully sever a linked device, whichever directions exist. removePeer drops
  // the peer we drive (and the reverse grant it minted); revokeDevice kills any
  // inbound grant we issued to this machine — including one from a separate
  // control-request approval, which removePeer does NOT cover. Both must run so
  // "Remove" truly severs both directions.
  const unlinkDevice = async (peerId?: string, deviceId?: string) => {
    if (peerId) await removePeer(peerId);
    if (deviceId) await revokeDevice(deviceId);
  };

  const addresses = config?.addresses ?? [];
  // Pick the selected pairing address (default: first / LAN).
  const selectedAddr =
    addresses.find((a) => a.host === addrHost) ?? addresses[0] ?? null;
  const gatewayUrl =
    selectedAddr?.gateway_url ?? config?.gateway_url ?? 'ws://<this-machine>:25314/ws/node';
  const hasTailscale = addresses.some((a) => a.label.startsWith('Tailscale'));

  // The exact command to run on the joining device.
  const hostCommand = `suzent node host --name "My Device" --url ${gatewayUrl}`;

  // One unified row per device, keyed by name, carrying every relationship:
  //   peer      → I can drive them (mode dropdown)
  //   deviceId  → they can drive me (a grant I issued; Revoke)
  //   isAgent / capabilities → currently connected as a WS node
  type DeviceRow = {
    key: string;
    name: string;
    platform?: string;
    online: boolean;
    isAgent: boolean;
    capabilities?: string;
    /** Live capability descriptors, present only while the node is connected —
     *  what the invoke form is generated from. */
    nodeId?: string;
    nodeCapabilities?: NodeCapabilityInfo[];
    deviceId?: string; // grant I issued (they drive me)
    scope?: string;
    status?: 'active' | 'paused'; // inbound grant status
    tokenHint?: string; // non-secret token fingerprint (head…tail)
    approvedAt?: string;
    triggerCount?: number; // inbound triggers received from this grant
    lastTriggeredAt?: string;
    peer?: ControlledPeer; // I drive them
    pendingGrant?: ControlRequest; // this device is requesting inbound control
  };
  // Normalize a base_url / addr to host:port so identities match across sides.
  const addrKeyOf = (u?: string): string | null => {
    if (!u) return null;
    try {
      const p = new URL(u.includes('://') ? u : `http://${u}`);
      return `addr:${p.hostname}:${p.port || '25314'}`;
    } catch {
      return null;
    }
  };
  const deviceRows: DeviceRow[] = (() => {
    const byKey = new Map<string, DeviceRow>();
    // Normalize the display name before matching: the same machine introduces
    // itself differently per source — "MacBook Pro" from a peer record vs
    // "MacBook-Pro.local" from mDNS — and those must collapse to one row.
    const keyForName = (s: string) =>
      `name:${s
        .trim()
        .toLowerCase()
        .replace(/\.local$/, '')
        .replace(/[\s_-]+/g, ' ')
        .trim()}`;
    // Merge peer.base_url and a grant's callback_url for the same machine
    // (names differ across sides). Shared normalizer defined above.
    const keyForUrl = addrKeyOf;
    for (const n of nodes) {
      const row: DeviceRow = {
        key: `node:${n.node_id}`,
        name: n.display_name,
        platform: n.platform,
        online: true,
        isAgent: isAgent(n),
        capabilities: capNames(n.capabilities),
        nodeId: n.node_id,
        nodeCapabilities: n.capabilities,
      };
      byKey.set(keyForName(n.display_name), row);
    }
    // Peers carry node_identity — the ONLY network-independent handle for a
    // machine. base_url changes between LAN and tailnet, and device/peer ids are
    // minted per side, so identity has to be indexed here or a grant arriving on
    // a different address spawns a second row for the same laptop.
    for (const p of peers) {
      const idKey = p.node_identity ? `id:${p.node_identity}` : null;
      const addrKey = keyForUrl(p.base_url);
      const nameKey = keyForName(p.name);
      const existing =
        (idKey && byKey.get(idKey)) ||
        (addrKey && byKey.get(addrKey)) ||
        byKey.get(nameKey);
      if (existing) {
        existing.peer = p;
        existing.online = existing.online || !!p.online;
        if (idKey) byKey.set(idKey, existing);
        if (addrKey) byKey.set(addrKey, existing);
      } else {
        const row: DeviceRow = {
          key: `peer:${p.peer_id}`,
          name: p.name,
          online: !!p.online,
          isAgent: false,
          peer: p,
        };
        byKey.set(nameKey, row);
        if (idKey) byKey.set(idKey, row);
        if (addrKey) byKey.set(addrKey, row);
      }
    }
    for (const d of devices) {
      // Host tokens are standalone credentials — never merged (key by device_id).
      if (d.scope === 'full') {
        byKey.set(`hosttoken:${d.device_id}`, {
          key: `dev:${d.device_id}`,
          name: d.display_name,
          platform: d.platform,
          online: d.connected,
          isAgent: false,
          deviceId: d.device_id,
          scope: d.scope,
          status: d.status,
          tokenHint: d.token_hint,
          approvedAt: d.approved_at,
        });
        continue;
      }
      // Merge a grant into the peer/node for the SAME machine: by stable
      // node_identity first (network-independent), then callback_url (address),
      // then name. Collapses the "MacBook Pro" peer and the "MacBook-Pro.local"
      // grant that name-matching alone would split.
      const idKey = d.node_identity ? `id:${d.node_identity}` : null;
      const addrKey = keyForUrl(d.callback_url);
      const nameKey = keyForName(d.display_name);
      const existing =
        (idKey && byKey.get(idKey)) ||
        (addrKey && byKey.get(addrKey)) ||
        byKey.get(nameKey);
      if (existing) {
        existing.deviceId = d.device_id;
        existing.scope = d.scope;
        existing.status = d.status;
        existing.tokenHint = d.token_hint;
        existing.approvedAt = d.approved_at;
        existing.triggerCount = d.trigger_count;
        existing.lastTriggeredAt = d.last_triggered_at;
        existing.online = existing.online || d.connected;
        if (idKey) byKey.set(idKey, existing);
      } else {
        const row: DeviceRow = {
          key: `dev:${d.device_id}`,
          name: d.display_name,
          platform: d.platform,
          online: d.connected,
          isAgent: false,
          deviceId: d.device_id,
          scope: d.scope,
          status: d.status,
          tokenHint: d.token_hint,
          approvedAt: d.approved_at,
          triggerCount: d.trigger_count,
          lastTriggeredAt: d.last_triggered_at,
        };
        byKey.set(nameKey, row);
        if (idKey) byKey.set(idKey, row);
      }
    }
    // Attach a pending inbound request to the existing row for the same machine
    // (by identity, then address, then name), so Approve/Deny shows inline
    // instead of a duplicate top card. Unmatched requests remain a top card.
    for (const g of grants) {
      const idK = g.controller_identity ? `id:${g.controller_identity}` : null;
      const ak = addrKeyOf(g.controller_addr);
      const row =
        (idK && byKey.get(idK)) ||
        (ak && byKey.get(ak)) ||
        byKey.get(keyForName(g.controller_name));
      if (row) row.pendingGrant = g;
    }
    // De-dup rows that were registered under multiple keys (addr + name).
    const seen = new Set<string>();
    const rows: DeviceRow[] = [];
    for (const row of byKey.values()) {
      if (seen.has(row.key)) continue;
      seen.add(row.key);
      rows.push(row);
    }
    return rows.sort(
      (a, b) => Number(b.online) - Number(a.online) || a.name.localeCompare(b.name)
    );
  })();

  // Pending requests NOT matched to an existing device row (genuinely new).
  const matchedGrantIds = new Set(
    deviceRows.filter((r) => r.pendingGrant).map((r) => r.pendingGrant!.request_id)
  );
  const unmatchedGrants = grants.filter((g) => !matchedGrantIds.has(g.request_id));

  return (
    <SettingsPage>
      <SettingsHeader
        title="Devices"
        subtitle="Connect and control trusted devices."
      />

      {error && (
        <div className="border-2 border-brutal-red bg-red-50 dark:bg-red-900/20 text-brutal-red px-3 py-2 text-xs font-mono">
          {error}
        </div>
      )}

      {/* Network status — the toggle lives in Mesh; this is read-only. */}
      <NetworkAccessStrip />

      {/* ── Discover peers ──────────────────────────────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          icon={<MagnifyingGlassIcon className="h-6 w-6" />}
          iconTone="blue"
          title="Discover"
          description="Find nearby or Tailscale devices."
          actions={
            <BrutalButton onClick={runDiscover} disabled={discovering} variant="dark">
              {discovering ? 'Scanning…' : 'Discover'}
            </BrutalButton>
          }
        />
        <div className="space-y-4">
          {discovered && (
            <>
              {([
                { key: 'lan', title: 'LAN (mDNS)', items: discovered.lan },
                { key: 'tailscale', title: 'Tailscale', items: discovered.tailscale },
              ] as const).map((group) => (
                <div key={group.key} className="space-y-2">
                  <div className="font-bold uppercase text-xs text-neutral-500 dark:text-neutral-400">
                    {group.title} ({group.items.length})
                  </div>
                  {group.items.length === 0 && (
                    <p className="text-xs text-neutral-400 font-mono pl-1">No peers found.</p>
                  )}
                  {group.items.map((peer) => {
                    const peerBase = peer.gateway_url
                      .replace(/^ws:\/\//, 'http://')
                      .replace(/^wss:\/\//, 'https://')
                      .replace(/\/ws\/node$/, '');
                    const peerHost = peer.host;
                    // Already linked if we control it under any address, or by name
                    // (it may be stored under a different network's address).
                    const already = peers.some(
                      (p) =>
                        p.base_url === peerBase ||
                        p.base_url.includes(peerHost) ||
                        p.name.toLowerCase() === peer.name.toLowerCase()
                    );
                    return (
                      <SettingsListItem key={peer.gateway_url} className="p-3">
                        <div className="flex items-center justify-between gap-3 w-full">
                          <div className="min-w-0">
                            <div className="font-bold truncate flex items-center gap-2">
                              <span className={`h-3 w-3 shrink-0 border border-brutal-black ${peer.reachable === false ? 'bg-neutral-300 dark:bg-zinc-700' : 'bg-brutal-green'}`} />
                              {peer.name}
                            </div>
                            <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate">
                              {peerBase}
                              {peer.reachable === false && <span className="text-neutral-400"> · unreachable (not running Suzent?)</span>}
                            </div>
                          </div>
                          <SettingsListAction
                            tone="blue"
                            disabled={busy === peerBase || already}
                            onClick={() => handleControl(peerBase, peer.name)}
                          >
                            {already ? 'Linked' : busy === peerBase ? 'Requesting…' : 'Control'}
                          </SettingsListAction>
                        </div>
                      </SettingsListItem>
                    );
                  })}
                </div>
              ))}
            </>
          )}

          {/* Zero-install path: scan and the screen joins the mesh. Placed
              above the CLI fallback because it is the one most devices can do. */}
          {selectedAddr?.host && (
            <div className="border-2 border-brutal-black bg-neutral-50 dark:border-white dark:bg-zinc-900">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs font-black uppercase tracking-wide hover:bg-neutral-100 dark:hover:bg-zinc-800"
                aria-expanded={showScreenPairing}
                onClick={() => setShowScreenPairing((open) => !open)}
              >
                <span>Add a screen (phone, tablet, TV)</span>
                <span aria-hidden="true">{showScreenPairing ? '−' : '+'}</span>
              </button>
              {showScreenPairing && (
                <div className="border-t-2 border-brutal-black p-3 dark:border-white">
                  {addresses.length > 1 && (
                    <div className="mb-3">
                      <BrutalSelect
                        value={selectedAddr.host}
                        onChange={setAddrHost}
                        options={addresses.map((a) => ({
                          value: a.host,
                          label: `${a.label} · ${a.host}`,
                        }))}
                      />
                    </div>
                  )}
                  <BrowserNodeQR host={selectedAddr.host} port={config?.port ?? 25314} />
                </div>
              )}
            </div>
          )}

          {/* Fallback for headless / non-discoverable devices. */}
          <details className="group">
            <summary className="cursor-pointer text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white">
              Pair manually
            </summary>
            <div className="space-y-2 mt-2">
              <p className="text-[11px] text-neutral-400 font-mono">Run on the other device.</p>
              {addresses.length > 1 && (
                <BrutalSelect
                  value={selectedAddr?.host ?? ''}
                  onChange={setAddrHost}
                  options={addresses.map((a) => ({ value: a.host, label: `${a.label} · ${a.host}` }))}
                />
              )}
              <div className="flex items-start gap-2">
                <pre className="flex-1 border-2 border-brutal-black dark:border-white bg-neutral-50 dark:bg-zinc-900 px-3 py-2 font-mono text-xs overflow-x-auto whitespace-pre-wrap break-all">
                  {hostCommand}
                </pre>
                <CopyButton value={hostCommand} tone="blue" />
              </div>
            </div>
          </details>
        </div>
      </SettingsCard>

      {/* ── Devices (one unified card) ──────────────────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          icon={<ComputerDesktopIcon className="h-6 w-6" />}
          iconTone="yellow"
          title={`Devices (${deviceRows.length})`}
          description="Linked devices and permissions."
        />
        <div className="space-y-3">
          {/* Rejected inbound trigger attempts — quiet by default; expandable
              for the operator who wants the details. */}
          {unauthorized.length > 0 && (
            <details className="text-[11px] font-mono text-neutral-400">
              <summary className="cursor-pointer hover:text-neutral-500 dark:hover:text-neutral-300 select-none">
                {unauthorized.length} blocked trigger attempt{unauthorized.length > 1 ? 's' : ''}
              </summary>
              <div className="mt-1 pl-3 space-y-0.5 text-neutral-400">
                {unauthorized.slice(-5).reverse().map((u, i) => (
                  <div key={i} className="truncate">
                    {relativeTime(u.at)} · from {u.client_host}
                    {u.claimed_id ? ` (claimed "${u.claimed_id}")` : ''}
                  </div>
                ))}
              </div>
            </details>
          )}
          {/* Incoming requests — another device wants to control this one. */}
          {unmatchedGrants.map((g) => (
            <SettingsListItem key={`grant:${g.request_id}`} className="p-4 border-brutal-blue">
              <div className="flex items-center justify-between gap-3 w-full">
                <div className="min-w-0">
                  <div className="font-bold truncate">
                    {g.controller_name}
                    <span className="text-neutral-400 font-normal"> ({g.controller_host || 'unknown'})</span>
                  </div>
                  <div className="text-xs text-brutal-blue font-mono truncate">
                    wants to control this device
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <SettingsListAction tone="blue" disabled={busy === g.request_id} onClick={() => act(g.request_id, () => approveGrant(g.request_id))}>
                    Approve
                  </SettingsListAction>
                  <SettingsListAction tone="red" disabled={busy === g.request_id} onClick={() => act(g.request_id, () => denyGrant(g.request_id))}>
                    Deny
                  </SettingsListAction>
                </div>
              </div>
            </SettingsListItem>
          ))}

          {/* Incoming WS companion pairings (phones etc.). */}
          {pending.map((p) => (
            <SettingsListItem key={`wspend:${p.pairing_code}`} className="p-4 border-brutal-blue">
              <div className="flex items-center justify-between gap-3 w-full">
                <div className="min-w-0">
                  <div className="font-bold truncate">
                    {p.display_name}{' '}
                    <span className="text-neutral-400 font-normal">({p.platform})</span>
                  </div>
                  <div className="text-xs text-brutal-blue font-mono truncate">
                    wants to connect · code {p.pairing_code}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <SettingsListAction tone="blue" disabled={busy === p.pairing_code} onClick={() => act(p.pairing_code, () => approvePendingNode(p.pairing_code))}>
                    Approve
                  </SettingsListAction>
                  <SettingsListAction tone="red" disabled={busy === p.pairing_code} onClick={() => act(p.pairing_code, () => denyPendingNode(p.pairing_code))}>
                    Deny
                  </SettingsListAction>
                </div>
              </div>
            </SettingsListItem>
          ))}

          {deviceRows.length === 0 && grants.length === 0 && pending.length === 0 && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
              No linked devices yet. Use Discover above to find and control another device.
            </p>
          )}

          {/* Established links — one row per device, two independent directions:
              Outbound (I control them — a status) and Inbound (they control me —
              a grant I own and can toggle). */}
          {deviceRows.map((d) => {
            const isHostToken = d.scope === 'full' && !d.peer;
            const hasOutbound = !!d.peer; // I can drive them
            // "They control me" is authorized by a grant I issued. An explicit
            // device grant (d.deviceId) is the source of truth; only fall back to
            // the peer's reverse_enabled flag when no device record exists yet.
            const hasInbound = !!d.deviceId; // I issued them a grant
            const inboundGranted = hasInbound
              ? d.status !== 'paused'
              : hasOutbound
                ? !!d.peer!.reverse_enabled
                : false;
            return (
              <SettingsListItem key={d.key}>
                <div className="flex w-full flex-col">
                  {/* Header: identity + badges + remove */}
                  <div className="flex items-center justify-between gap-3 border-b-2 border-brutal-black bg-white px-4 py-3 dark:bg-zinc-800">
                    <div className="min-w-0 flex items-center gap-2">
                      {!isHostToken && (
                        <span
                          className={`h-3 w-3 shrink-0 border border-brutal-black ${d.online ? 'bg-brutal-green' : 'bg-neutral-300 dark:bg-zinc-700'}`}
                          title={d.online ? 'Online' : 'Offline'}
                        />
                      )}
                      <span className="font-bold truncate">{d.name}</span>
                      {d.platform && !isHostToken && <span className="text-neutral-400 font-normal text-sm">{d.platform}</span>}
                      {d.isAgent && (
                        <span className="border border-brutal-black bg-brutal-blue px-1.5 py-0.5 text-[10px] font-black uppercase text-white">Agent</span>
                      )}
                      {d.scope === 'full' && (
                        <span className="border border-brutal-black bg-brutal-red px-1.5 py-0.5 text-[10px] font-black uppercase text-white">Host</span>
                      )}
                    </div>
                    {isHostToken && d.deviceId ? (
                      <SettingsListAction tone="red" disabled={busy === d.deviceId} onClick={() => act(d.deviceId!, () => revokeDevice(d.deviceId!))}>
                        Revoke
                      </SettingsListAction>
                    ) : (hasOutbound || hasInbound) ? (
                      <SettingsListAction
                        tone="red"
                        disabled={busy === (d.peer?.peer_id ?? d.deviceId)}
                        onClick={() => act(d.peer?.peer_id ?? d.deviceId!, () => unlinkDevice(d.peer?.peer_id, d.deviceId))}
                      >
                        Remove
                      </SettingsListAction>
                    ) : null}
                  </div>

                  <div className="space-y-3 px-4 py-3">
                    {/* Drive this device from here: a Suzent peer takes a prompt
                        for its agent, a node takes one of its named commands. */}
                    {d.peer && (
                      <>
                        <PeerTriggerPanel
                          peerId={d.peer.peer_id}
                          paused={d.peer.mode !== 'trigger'}
                        />
                        {/* A Suzent peer runs its own nodes, so its hardware is
                            invokable too — loaded on demand, not on the poll. */}
                        <PeerInvokePanel peerId={d.peer.peer_id} />
                      </>
                    )}

                    {d.nodeId && (d.nodeCapabilities?.length ?? 0) > 0 && (
                      <NodeInvokePanel
                        nodeId={d.nodeId}
                        capabilities={d.nodeCapabilities ?? []}
                      />
                    )}

                    {d.peer?.base_url && (
                      <div className="border-l-4 border-brutal-blue bg-white/80 px-2 py-1 text-[11px] text-neutral-500 font-mono truncate dark:bg-zinc-950/50 dark:text-neutral-400">{d.peer.base_url}</div>
                    )}

                    {/* Inbound usage: how often / when this grant last drove us. */}
                    {hasInbound && (d.triggerCount ?? 0) > 0 && (
                      <div className="text-[11px] text-neutral-400 font-mono">
                        Triggered you {d.triggerCount}×
                        {d.lastTriggeredAt ? ` · last ${relativeTime(d.lastTriggeredAt)}` : ''}
                      </div>
                    )}

                    {/* Host token: full-access credential — no direction grid. */}
                    {isHostToken && (
                      <div className="border-l-4 border-brutal-red bg-white/80 px-2 py-1 text-[11px] text-neutral-500 font-mono dark:bg-zinc-950/50 dark:text-neutral-400">
                        Full-access credential
                        {d.tokenHint ? ` · ${d.tokenHint}` : ''}
                        {d.approvedAt ? ` · created ${d.approvedAt.slice(0, 10)}` : ''}
                      </div>
                    )}

                    {/* Two-direction grid */}
                    {!isHostToken && (
                      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                        {/* Outbound — I control them (status only) */}
                        <div className="flex items-center justify-between gap-3 border-2 border-brutal-black bg-white px-3 py-2 dark:bg-zinc-900">
                          <span className="text-[10px] uppercase tracking-wide text-neutral-400 font-black">
                            I control them
                          </span>
                          {hasOutbound && d.peer ? (
                            (() => {
                              const st = d.peer.outbound_status
                                ?? (d.online ? 'ready' : 'offline');
                              if (st === 'revoked') {
                                return (
                                  <span className="flex items-center gap-2">
                                    <StatusPill tone="red" label="Revoked" />
                                    <button
                                      className="text-[10px] text-brutal-blue font-black uppercase hover:underline disabled:opacity-40"
                                      disabled={busy === d.peer.base_url}
                                      onClick={() => handleControl(d.peer!.base_url, d.peer!.name)}
                                    >
                                      Re-request
                                    </button>
                                  </span>
                                );
                              }
                              return (
                                <StatusPill
                                  tone={st === 'ready' ? 'green' : 'neutral'}
                                  label={st === 'ready' ? 'Ready' : 'Offline'}
                                />
                              );
                            })()
                          ) : (
                            <StatusPill tone="neutral" label="—" />
                          )}
                        </div>

                        {/* Inbound — they control me (toggle I own) */}
                        <div className="flex items-center justify-between gap-3 border-2 border-brutal-black bg-white px-3 py-2 dark:bg-zinc-900">
                          <span className="text-[10px] uppercase tracking-wide text-neutral-400 font-black">
                            They control me
                          </span>
                          {d.pendingGrant ? (
                            // This machine is asking for inbound control — approve/deny
                            // inline instead of a separate top card.
                            <div className="flex items-center gap-1.5 shrink-0">
                              <button
                                className="text-[10px] text-brutal-green font-black uppercase hover:underline disabled:opacity-40"
                                disabled={busy === d.pendingGrant.request_id}
                                onClick={() => act(d.pendingGrant!.request_id, () => approveGrant(d.pendingGrant!.request_id))}
                              >
                                Approve
                              </button>
                              <span className="text-neutral-300">·</span>
                              <button
                                className="text-[10px] text-brutal-red font-black uppercase hover:underline disabled:opacity-40"
                                disabled={busy === d.pendingGrant.request_id}
                                onClick={() => act(d.pendingGrant!.request_id, () => denyGrant(d.pendingGrant!.request_id))}
                              >
                                Deny
                              </button>
                            </div>
                          ) : hasInbound && d.deviceId ? (
                            // A grant I issued (the real inbound authorization) —
                            // pause/resume without dropping the token. Fully severing
                            // is the row's single "Remove" button (header).
                            <DirectionToggle
                              on={inboundGranted}
                              busy={busy === d.deviceId}
                              onToggle={() => act(d.deviceId!, () => setDeviceStatus(d.deviceId!, inboundGranted ? 'paused' : 'active'))}
                            />
                          ) : hasOutbound && d.peer ? (
                            // No issued grant yet — offer to mint a reverse grant so
                            // this peer we drive can drive us back.
                            <DirectionToggle
                              on={inboundGranted}
                              busy={busy === `rev:${d.peer.peer_id}`}
                              onToggle={() => act(`rev:${d.peer!.peer_id}`, () => setPeerReverse(d.peer!.peer_id, !inboundGranted))}
                            />
                          ) : (
                            <StatusPill tone="neutral" label="—" />
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </SettingsListItem>
            );
          })}
        </div>
      </SettingsCard>
    </SettingsPage>
  );
}
