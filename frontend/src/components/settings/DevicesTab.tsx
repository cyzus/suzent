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
  connectNode,
  fetchConnections,
  type ConnectedNode,
  type PendingNode,
  type ApprovedDevice,
  type NodeAuthConfig,
  type DiscoveredPeer,
  type OutboundConnection,
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
  const [showToken, setShowToken] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [restartHint, setRestartHint] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [addrHost, setAddrHost] = useState<string | null>(null);
  const [connections, setConnections] = useState<OutboundConnection[]>([]);
  const [discovered, setDiscovered] = useState<{ lan: DiscoveredPeer[]; tailscale: DiscoveredPeer[] } | null>(null);
  const [discovering, setDiscovering] = useState(false);

  const refresh = useCallback(async () => {
    const [n, p, d, c] = await Promise.all([
      fetchNodes(),
      fetchPendingNodes(),
      fetchApprovedDevices(),
      fetchConnections(),
    ]);
    setNodes(n);
    setPending(p);
    setDevices(d);
    setConnections(c);
    setLoaded(true);
  }, []);

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
    async (updates: { node_auth_mode?: string; node_auth_token?: string; regenerate?: boolean; node_lan_bind?: boolean }) => {
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

  const mode = config?.node_auth_mode ?? 'open';
  const addresses = config?.addresses ?? [];
  // Pick the selected pairing address (default: first / LAN).
  const selectedAddr =
    addresses.find((a) => a.host === addrHost) ?? addresses[0] ?? null;
  const gatewayUrl =
    selectedAddr?.gateway_url ?? config?.gateway_url ?? 'ws://<this-machine>:25314/ws/node';
  const hasTailscale = addresses.some((a) => a.label.startsWith('Tailscale'));

  // The exact command to run on the joining device.
  const hostCommand =
    `suzent node host --name "My Device" --url ${gatewayUrl}` +
    (mode === 'token' ? ` --token ${config?.node_auth_token || '<shared-secret>'}` : '');

  // Unified device list: online nodes + durably-approved devices, keyed by name.
  // deviceId is set only when a durable token exists (i.e. Revoke applies).
  type MergedDevice = {
    key: string;
    name: string;
    platform: string;
    online: boolean;
    isAgent: boolean;
    capabilities?: string;
    deviceId?: string;
    approvedAt?: string;
  };
  const mergedDevices: MergedDevice[] = (() => {
    const byName = new Map<string, MergedDevice>();
    for (const n of nodes) {
      byName.set(n.display_name, {
        key: `node:${n.node_id}`,
        name: n.display_name,
        platform: n.platform,
        online: true,
        isAgent: isAgent(n),
        capabilities: capNames(n.capabilities),
      });
    }
    for (const d of devices) {
      const existing = byName.get(d.display_name);
      if (existing) {
        existing.deviceId = d.device_id;
        existing.approvedAt = d.approved_at;
        existing.online = existing.online || d.connected;
      } else {
        byName.set(d.display_name, {
          key: `dev:${d.device_id}`,
          name: d.display_name,
          platform: d.platform,
          online: d.connected,
          isAgent: false,
          deviceId: d.device_id,
          approvedAt: d.approved_at,
        });
      }
    }
    // Online first, then by name.
    return [...byName.values()].sort(
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
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="font-bold uppercase text-sm">Auth mode</div>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono max-w-md">
                {mode === 'open' && 'Any device that can reach this server may connect. Use only on a trusted network.'}
                {mode === 'token' && 'Devices must present the shared secret below.'}
                {mode === 'approve' && 'New devices must be approved here; approved devices reconnect silently.'}
              </p>
            </div>
            <BrutalSelect
              value={mode}
              onChange={(v) => updateConfig({ node_auth_mode: v })}
              options={[
                { value: 'open', label: 'Open' },
                { value: 'token', label: 'Token' },
                { value: 'approve', label: 'Approve' },
              ]}
            />
          </div>

          {mode === 'token' && (
            <div className="space-y-2">
              <div className="font-bold uppercase text-sm">Shared secret</div>
              <div className="flex items-center gap-2">
                <input
                  type={showToken ? 'text' : 'password'}
                  value={config?.node_auth_token ?? ''}
                  readOnly
                  placeholder="No token set — generate one"
                  className="flex-1 border-2 border-brutal-black dark:border-white bg-transparent px-3 py-2 font-mono text-xs"
                />
                <SettingsListAction onClick={() => setShowToken((s) => !s)}>
                  {showToken ? 'Hide' : 'Show'}
                </SettingsListAction>
                <CopyButton value={config?.node_auth_token ?? ''} tone="blue" />
                <BrutalButton onClick={() => updateConfig({ regenerate: true })}>
                  Regenerate
                </BrutalButton>
              </div>
            </div>
          )}

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

          <p className="text-[11px] text-neutral-500 dark:text-neutral-400 font-mono">
            ⚠ ws:// traffic is plaintext, and "reachable by other devices" exposes the HTTP API on your network — keep it to a trusted LAN or tailnet, and use Token/Approve auth.
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
              Scan the LAN (mDNS) and your tailnet for Suzent peers. Discovery only finds the address — the remote still gates the connection by its auth mode.
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
                    const already = connections.some((c) => c.gateway_url === peer.gateway_url);
                    return (
                      <SettingsListItem key={peer.gateway_url}>
                        <div className="flex items-center justify-between gap-3 w-full">
                          <div className="min-w-0">
                            <div className="font-bold truncate flex items-center gap-2">
                              <span className={peer.reachable === false ? 'text-neutral-400' : 'text-brutal-green'}>●</span>
                              {peer.name}
                            </div>
                            <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate">
                              {peer.gateway_url}{peer.auth_mode ? ` · ${peer.auth_mode}` : ''}
                              {peer.reachable === false && <span className="text-neutral-400"> · unreachable (not running Suzent?)</span>}
                            </div>
                          </div>
                          <SettingsListAction
                            tone="blue"
                            disabled={busy === peer.gateway_url || already}
                            onClick={() => act(peer.gateway_url, () => connectNode(peer.gateway_url))}
                          >
                            {already ? 'Connecting' : 'Connect'}
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

      {/* ── Pending approvals ───────────────────────────────────────── */}
      {(mode === 'approve' || pending.length > 0) && (
        <SettingsCard>
          <SectionCardHeader
            title={`Pending approval (${pending.length})`}
            description="Devices waiting for you to approve their connection."
          />
          <div className="space-y-2 mt-3">
            {pending.length === 0 && (
              <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
                Nothing waiting. Run the connect command above on another device and its pairing code will appear here.
              </p>
            )}
            {pending.map((p) => (
              <SettingsListItem key={p.pairing_code}>
                <div className="flex items-center justify-between gap-3 w-full">
                  <div className="min-w-0">
                    <div className="font-bold truncate">
                      {p.display_name}{' '}
                      <span className="text-neutral-400 font-normal">({p.platform})</span>
                    </div>
                    <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate">
                      code <span className="text-brutal-black dark:text-white font-bold">{p.pairing_code}</span> · {capNames(p.capabilities)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <SettingsListAction
                      tone="blue"
                      disabled={busy === p.pairing_code}
                      onClick={() => act(p.pairing_code, () => approvePendingNode(p.pairing_code))}
                    >
                      Approve
                    </SettingsListAction>
                    <SettingsListAction
                      tone="red"
                      disabled={busy === p.pairing_code}
                      onClick={() => act(p.pairing_code, () => denyPendingNode(p.pairing_code))}
                    >
                      Deny
                    </SettingsListAction>
                  </div>
                </div>
              </SettingsListItem>
            ))}
          </div>
        </SettingsCard>
      )}

      {/* ── Devices (connected + approved, unified) ─────────────────── */}
      <SettingsCard>
        <SectionCardHeader
          title={`Devices (${mergedDevices.length})`}
          description="Online and approved devices. AGENT = exposes its own agent. Revoke removes an approved device's durable token."
        />
        <div className="space-y-2 mt-3">
          {mergedDevices.length === 0 && (
            <p className="text-xs text-neutral-500 dark:text-neutral-400 font-mono">
              No devices yet.
            </p>
          )}
          {mergedDevices.map((d) => (
            <SettingsListItem key={d.key}>
              <div className="flex items-center justify-between gap-3 w-full">
                <div className="min-w-0">
                  <div className="font-bold truncate flex items-center gap-2">
                    <span className={d.online ? 'text-brutal-green' : 'text-neutral-400'}>●</span>
                    {d.name}
                    <span className="text-neutral-400 font-normal">({d.platform})</span>
                    {d.isAgent && (
                      <span className="px-1.5 py-0.5 text-[10px] font-black uppercase border border-brutal-blue text-brutal-blue rounded-sm">
                        Agent
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-neutral-500 dark:text-neutral-400 font-mono truncate">
                    {d.online ? (d.capabilities || 'online') : 'offline'}
                    {d.approvedAt && <> · approved {d.approvedAt.slice(0, 10)}</>}
                  </div>
                </div>
                {d.deviceId && (
                  <SettingsListAction
                    tone="red"
                    disabled={busy === d.deviceId}
                    onClick={() => act(d.deviceId!, () => revokeDevice(d.deviceId!))}
                  >
                    Revoke
                  </SettingsListAction>
                )}
              </div>
            </SettingsListItem>
          ))}
        </div>
      </SettingsCard>
    </div>
  );
}
