import React, { useCallback, useEffect, useState } from 'react';

import {
  fetchNodes,
  fetchPendingNodes,
  fetchApprovedDevices,
  fetchNodeConfig,
  saveNodeConfig,
  approvePendingNode,
  denyPendingNode,
  revokeDevice,
  discoverNodes,
  fetchConnections,
  fetchGrants,
  approveGrant,
  denyGrant,
  fetchPeers,
  setPeerMode,
  removePeer,
  requestControl,
  controlStatus,
  createHostToken,
  type ConnectedNode,
  type PendingNode,
  type ApprovedDevice,
  type NodeAuthConfig,
  type DiscoveredPeer,
  type OutboundConnection,
  type ControlRequest,
  type ControlledPeer,
} from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalButton } from '../BrutalButton';
import { BrutalOnOff } from '../BrutalOnOff';
import { SettingsHeader } from './SettingsHeader';
import { SectionCardHeader, SettingsCard, SettingsListItem, SettingsListAction } from './SettingsCard';

const POLL_MS = 4000;
const AGENT_CAPABILITY = 'agent.run';

function capNames(caps: { name: string }[]): string {
  return caps.length ? caps.map((c) => c.name).join(', ') : 'none';
}

function isAgent(node: { capabilities: { name: string }[] }): boolean {
  return node.capabilities.some((c) => c.name === AGENT_CAPABILITY);
}

/** A small button that confirms it copied to the clipboard. */
function CopyButton({ value, tone = 'neutral', label = 'Copy' }: { value: string; tone?: 'blue' | 'red' | 'neutral'; label?: string }): React.ReactElement {
  const [copied, setCopied] = useState(false);
  return (
    <SettingsListAction
      tone={tone}
      disabled={!value}
      onClick={() => {
        if (!value) return;
        navigator.clipboard?.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? 'Copied' : label}
    </SettingsListAction>
  );
}

export function DevicesTab(): React.ReactElement {
  const [nodes, setNodes] = useState<ConnectedNode[]>([]);
  const [pending, setPending] = useState<PendingNode[]>([]);
  const [devices, setDevices] = useState<ApprovedDevice[]>([]);
  const [config, setConfig] = useState<NodeAuthConfig | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restartHint, setRestartHint] = useState(false);
  const [hostToken, setHostToken] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [addrHost, setAddrHost] = useState<string | null>(null);
  const [connections, setConnections] = useState<OutboundConnection[]>([]);
  const [grants, setGrants] = useState<ControlRequest[]>([]);
  const [peers, setPeers] = useState<ControlledPeer[]>([]);
  const [discovered, setDiscovered] = useState<{ lan: DiscoveredPeer[]; tailscale: DiscoveredPeer[] } | null>(null);
  const [discovering, setDiscovering] = useState(false);

  const refresh = useCallback(async () => {
    const [n, p, d, c, g, pe] = await Promise.all([
      fetchNodes(),
      fetchPendingNodes(),
      fetchApprovedDevices(),
      fetchConnections(),
      fetchGrants(),
      fetchPeers(),
    ]);
    setNodes(n);
    setPending(p);
    setDevices(d);
    setConnections(c);
    setGrants(g);
    setPeers(pe);
    setLoaded(true);
  }, []);

  // Connect = "I want to control this device": request a grant, poll until the
  // peer's operator approves, then it appears under "Controlling".
  const handleControl = useCallback(
    async (baseUrl: string, name = '') => {
      setBusy(baseUrl);
      setError(null);
      try {
        const { request_id, base_url } = await requestControl(baseUrl);
        for (let i = 0; i < 90; i++) {
          const s = await controlStatus(base_url, request_id, name);
          if (s.status === 'approved') break;
          if (s.status === 'denied' || s.status === 'expired') {
            setError(`Control request ${s.status}.`);
            break;
          }
          await new Promise((r) => setTimeout(r, 2000));
        }
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

  const updateConfig = useCallback(
    async (updates: { node_lan_bind?: boolean }) => {
      setError(null);
      try {
        const next = await saveNodeConfig(updates);
        if (next.restart_required) setRestartHint(true);
        // Preserve pairing-address fields the POST response doesn't echo.
        setConfig((prev) => ({ ...(prev ?? {}), ...next }));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    []
  );

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
    deviceId?: string; // grant I issued (they drive me)
    scope?: string;
    approvedAt?: string;
    peer?: ControlledPeer; // I drive them
  };
  const deviceRows: DeviceRow[] = (() => {
    const byKey = new Map<string, DeviceRow>();
    const keyFor = (s: string) => s.trim().toLowerCase();
    for (const n of nodes) {
      byKey.set(keyFor(n.display_name), {
        key: `node:${n.node_id}`,
        name: n.display_name,
        platform: n.platform,
        online: true,
        isAgent: isAgent(n),
        capabilities: capNames(n.capabilities),
      });
    }
    for (const d of devices) {
      const k = keyFor(d.display_name);
      const ex = byKey.get(k);
      if (ex) {
        ex.deviceId = d.device_id;
        ex.scope = d.scope;
        ex.approvedAt = d.approved_at;
        ex.online = ex.online || d.connected;
      } else {
        byKey.set(k, {
          key: `dev:${d.device_id}`,
          name: d.display_name,
          platform: d.platform,
          online: d.connected,
          isAgent: false,
          deviceId: d.device_id,
          scope: d.scope,
          approvedAt: d.approved_at,
        });
      }
    }
    for (const p of peers) {
      const k = keyFor(p.name);
      const ex = byKey.get(k);
      if (ex) {
        ex.peer = p;
        ex.online = ex.online || !!p.online;
      } else {
        byKey.set(k, {
          key: `peer:${p.peer_id}`,
          name: p.name,
          online: !!p.online,
          isAgent: false,
          peer: p,
        });
      }
    }
    return [...byKey.values()].sort(
      (a, b) => Number(b.online) - Number(a.online) || a.name.localeCompare(b.name)
    );
  })();

  return (
    <div className="space-y-6">
      <SettingsHeader
        title="Devices"
        subtitle="Companion devices and peer agents connected to this Suzent."
        actions={
          <div className="flex items-center gap-2">
            {loaded && (
              <span className="text-[10px] uppercase tracking-wide text-neutral-400 font-mono">
                auto-refresh
              </span>
            )}
            <SettingsListAction onClick={() => refresh()}>Refresh</SettingsListAction>
          </div>
        }
      />

      {error && (
        <div className="border-2 border-brutal-red bg-red-50 dark:bg-red-900/20 text-brutal-red px-3 py-2 text-xs font-mono">
          {error}
        </div>
      )}

      {/* ── Connection auth ─────────────────────────────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          title="Connection auth"
          description="How companion devices are allowed to connect to this server."
        />
        <div className="space-y-4 mt-3">
          <div>
            <div className="font-bold uppercase text-sm">Auth mode</div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono max-w-md">
              New devices must be approved here before they can connect; once
              approved they reconnect silently. Approve from the desktop app or
              with <code>suzent node approve &lt;code&gt;</code> on the CLI.
            </p>
          </div>

          <div className="flex items-center justify-between gap-4 border-t border-brutal-black/10 dark:border-white/10 pt-3">
            <div>
              <div className="font-bold uppercase text-sm">Reachable by other devices</div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono max-w-md">
                Bind the server to all interfaces so peers can connect. Off by
                default the app listens on localhost only — required for
                cross-device nodes. Takes effect after a restart.
              </p>
            </div>
            <BrutalOnOff
              checked={!!config?.node_lan_bind}
              onChange={(v) => updateConfig({ node_lan_bind: v })}
            />
          </div>

          {restartHint && (
            <div className="border-2 border-brutal-black dark:border-white bg-brutal-yellow/40 px-3 py-2 text-xs font-mono">
              Restart Suzent on this device for the network-binding change to take effect.
            </div>
          )}

          <div className="flex items-center justify-between gap-4 border-t border-brutal-black/10 dark:border-white/10 pt-3">
            <div>
              <div className="font-bold uppercase text-sm">Remote host access</div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono max-w-md">
                Mint a <span className="font-bold">full-access</span> token to operate this device remotely (everything, not just the agent). Granted control tokens stay scoped to the agent only.
              </p>
            </div>
            <BrutalButton
              onClick={async () => {
                setError(null);
                try {
                  const { token } = await createHostToken('Host access');
                  setHostToken(token);
                  await refresh();
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              Create host token
            </BrutalButton>
          </div>
          {hostToken && (
            <div className="border-2 border-brutal-red px-3 py-2 space-y-1">
              <div className="text-[11px] font-bold uppercase text-brutal-red">Copy now — shown once</div>
              <div className="flex items-center gap-2">
                <code className="flex-1 font-mono text-xs break-all">{hostToken}</code>
                <CopyButton value={hostToken} tone="red" />
                <SettingsListAction onClick={() => setHostToken(null)}>Dismiss</SettingsListAction>
              </div>
              <p className="text-[11px] text-neutral-400 font-mono">
                On the remote device, send it as <code>Authorization: Bearer &lt;token&gt;</code>. Revoke it anytime under Devices.
              </p>
            </div>
          )}

          <p className="text-[11px] text-neutral-500 dark:text-neutral-400 font-mono">
            ⚠ ws:// traffic is plaintext, and "reachable by other devices" exposes the HTTP API on your network — keep it to a trusted LAN or tailnet.
          </p>
        </div>
      </SettingsCard>

      {/* ── Discover peers ──────────────────────────────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          title="Discover"
          description="Find other Suzent instances on your network and join them from here."
          actions={
            <BrutalButton onClick={runDiscover} disabled={discovering}>
              {discovering ? 'Scanning…' : 'Discover'}
            </BrutalButton>
          }
        />
        <div className="space-y-4 mt-3">
          {!discovered && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
              Scan the LAN (mDNS) and your tailnet for Suzent peers. Discovery only finds the address — the remote still approves the connection.
            </p>
          )}
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
                      <SettingsListItem key={peer.gateway_url}>
                        <div className="flex items-center justify-between gap-3 w-full">
                          <div className="min-w-0">
                            <div className="font-bold truncate flex items-center gap-2">
                              <span className={peer.reachable === false ? 'text-neutral-400' : 'text-brutal-green'}>●</span>
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

          {/* Fallback for headless / non-discoverable devices. */}
          <details className="group">
            <summary className="cursor-pointer text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 hover:text-brutal-black dark:hover:text-white">
              Pair manually
            </summary>
            <div className="space-y-2 mt-2">
              <p className="text-[11px] text-neutral-400 font-mono">
                Run this on the other device to make it a node of this one (useful for headless servers).
              </p>
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
          title={`Devices (${deviceRows.length})`}
          description="Every device this one is linked to. Requests to approve appear at the top; each linked device shows its direction and controls."
        />
        <div className="space-y-2 mt-3">
          {/* Incoming requests — another device wants to control this one. */}
          {grants.map((g) => (
            <SettingsListItem key={`grant:${g.request_id}`}>
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
            <SettingsListItem key={`wspend:${p.pairing_code}`}>
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

          {/* Established links — one row per device, both directions. */}
          {deviceRows.map((d) => {
            const drivesThem = !!d.peer; // I can drive them
            const drivenByMe = !!d.deviceId && !d.peer; // they drive me (one-way inbound)
            const dirLabel = drivenByMe
              ? 'can control this device'
              : d.online
                ? (d.capabilities || 'online')
                : 'offline';
            return (
              <SettingsListItem key={d.key}>
                <div className="flex items-center justify-between gap-3 w-full">
                  <div className="min-w-0">
                    <div className="font-bold truncate flex items-center gap-2">
                      <span className={d.online ? 'text-brutal-green' : 'text-neutral-400'}>●</span>
                      {d.name}
                      {d.platform && <span className="text-neutral-400 font-normal">({d.platform})</span>}
                      {d.isAgent && (
                        <span className="px-1.5 py-0.5 text-[10px] font-black uppercase border border-brutal-blue text-brutal-blue rounded-sm">Agent</span>
                      )}
                      {d.scope === 'full' && (
                        <span className="px-1.5 py-0.5 text-[10px] font-black uppercase border border-brutal-red text-brutal-red rounded-sm">Host</span>
                      )}
                    </div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate">
                      {dirLabel}
                      {d.peer?.base_url ? ` · ${d.peer.base_url}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {drivesThem && d.peer && (
                      <BrutalSelect
                        value={d.peer.mode}
                        onChange={(m) => act(d.peer!.peer_id, () => setPeerMode(d.peer!.peer_id, m))}
                        options={[
                          { value: 'one_way', label: 'Trigger them' },
                          { value: 'mutual', label: 'Mutual' },
                          { value: 'paused', label: 'Paused' },
                        ]}
                      />
                    )}
                    {drivesThem && d.peer && (
                      <SettingsListAction tone="red" disabled={busy === d.peer.peer_id} onClick={() => act(d.peer!.peer_id, () => removePeer(d.peer!.peer_id))}>
                        Remove
                      </SettingsListAction>
                    )}
                    {drivenByMe && d.deviceId && (
                      <SettingsListAction tone="red" disabled={busy === d.deviceId} onClick={() => act(d.deviceId!, () => revokeDevice(d.deviceId!))}>
                        Revoke
                      </SettingsListAction>
                    )}
                  </div>
                </div>
              </SettingsListItem>
            );
          })}
        </div>
      </SettingsCard>
    </div>
  );
}
