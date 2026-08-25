import React, { useCallback, useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import {
  fetchNodeConfig,
  fetchA2AStatus,
  saveNodeConfig,
  type NodeAuthConfig,
  type A2AStatus,
} from '../../lib/api';
import { BrutalOnOff } from '../BrutalOnOff';
import { SettingsCard, SectionCardHeader } from './SettingsCard';

/**
 * Canonical network-access card: the bind toggle and an exposure table showing
 * what each surface is doing. Lives in the Mesh tab; Devices shows a read-only
 * summary that links here.
 *
 * Self-contained: fetches its own config so it can be placed in any tab without
 * prop drilling through SettingsModal.
 */
export function NetworkAccessCard(): React.ReactElement {
  const [config, setConfig] = useState<NodeAuthConfig | null>(null);
  const [a2a, setA2a] = useState<A2AStatus | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [c, s] = await Promise.all([
      fetchNodeConfig().catch(() => null),
      fetchA2AStatus().catch(() => null),
    ]);
    setConfig(c);
    setA2a(s);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggle = useCallback(async (enabled: boolean) => {
    setError(null);
    try {
      const next = await saveNodeConfig({ node_lan_bind: enabled });
      setConfig((prev) => ({ ...(prev ?? {}), ...next }));
      if (next.restart_required) {
        setRestarting(true);
        await new Promise((r) => setTimeout(r, 150));
        await invoke('restart_app');
      }
    } catch (e) {
      setRestarting(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const bound = !!config?.node_lan_bind;
  const active = !!config?.binding_active;

  type Surface = { name: string; path: string; live: boolean; note?: string };
  const surfaces: Surface[] = [
    { name: 'Node gateway', path: '/ws/node', live: bound },
    { name: 'Peer channel', path: '/channels/suzent/*', live: bound },
    {
      name: 'A2A agent card',
      path: '/.well-known/agent-card.json',
      live: bound && !!a2a?.enabled,
      note: !a2a?.enabled ? 'not published' : undefined,
    },
    { name: 'Browser node', path: '/node', live: bound },
  ];

  return (
    <SettingsCard>
      <SectionCardHeader
        icon={
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8.288 15.038a5.25 5.25 0 017.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 011.06 0z"
            />
          </svg>
        }
        iconTone="green"
        title="Network access"
        description="Expose this device on your LAN or tailnet so other devices and agents can reach it."
        actions={<BrutalOnOff checked={bound} disabled={restarting} onChange={toggle} />}
      />

      {restarting && (
        <div className="border-2 border-brutal-black bg-brutal-yellow/40 px-3 py-2 text-xs font-bold uppercase mb-3">
          Restarting Suzent to apply network access…
        </div>
      )}

      {error && (
        <div className="border-2 border-brutal-red bg-red-50 dark:bg-red-900/20 text-brutal-red px-3 py-2 text-xs font-mono mb-3">
          {error}
        </div>
      )}

      {bound && active && (
        <div className="border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 text-xs font-mono">
          {surfaces.map((s) => (
            <div
              key={s.path}
              className="flex items-center justify-between px-3 py-1.5 border-b last:border-b-0 border-brutal-black/10 dark:border-white/10"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={`w-2 h-2 border border-brutal-black shrink-0 ${
                    s.live ? 'bg-brutal-green' : 'bg-neutral-300 dark:bg-zinc-600'
                  }`}
                />
                <span className="font-bold">{s.name}</span>
                <span className="text-neutral-500 truncate">{s.path}</span>
              </div>
              <span className="text-[10px] font-bold uppercase text-neutral-500 shrink-0">
                {s.note ?? (s.live ? 'live' : 'off')}
              </span>
            </div>
          ))}
        </div>
      )}

      {bound && !active && (
        <p className="text-xs text-brutal-red font-bold uppercase">Restart needed</p>
      )}

      {!bound && (
        <p className="text-xs text-neutral-500">
          Listening on 127.0.0.1 only. Other devices cannot reach this machine until you enable
          network access.
        </p>
      )}

      <p className="mt-3 border-l-4 border-brutal-yellow bg-brutal-yellow/20 px-3 py-2 text-[11px] text-neutral-600 dark:text-neutral-300 font-mono">
        Use only on a trusted LAN or Tailscale network.
      </p>
    </SettingsCard>
  );
}

/**
 * Compact read-only strip for tabs that aren't the canonical home (Devices).
 * Shows status and links conceptually to Mesh for changes.
 */
export function NetworkAccessStrip(): React.ReactElement {
  const [config, setConfig] = useState<NodeAuthConfig | null>(null);

  useEffect(() => {
    fetchNodeConfig()
      .then(setConfig)
      .catch(() => {});
  }, []);

  const bound = !!config?.node_lan_bind;
  const active = !!config?.binding_active;

  return (
    <div className="flex items-center justify-between gap-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2">
      <div className="flex items-center gap-2 text-xs">
        <span
          className={`w-2.5 h-2.5 border border-brutal-black ${
            bound && active
              ? 'bg-brutal-green'
              : bound
                ? 'bg-brutal-yellow'
                : 'bg-neutral-300 dark:bg-zinc-600'
          }`}
        />
        <span className="font-bold uppercase">
          {bound && active
            ? `Listening on 0.0.0.0:${config?.port ?? 25314}`
            : bound
              ? 'Restart needed'
              : 'Loopback only'}
        </span>
      </div>
      <span className="text-[10px] text-neutral-500 uppercase font-bold">Manage in Mesh tab</span>
    </div>
  );
}
