import React, { useEffect, useMemo, useState } from 'react';
import {
  fetchPeerCapabilities,
  invokeNode,
  invokePeerCapability,
  type NodeCapabilityInfo,
} from '../../lib/api';
import { BrutalSelect } from '../BrutalSelect';
import { SettingsListAction } from './SettingsCard';

type InvokeFn = (
  command: string,
  params: Record<string, unknown>
) => Promise<{ success: boolean; result?: unknown; error?: string | null }>;

/**
 * Run a capability on a device, straight from the app.
 *
 * The form is generated from the capability's own `params_schema` — the device
 * declared it at handshake, so there is nothing per-device to hardcode. A new
 * node type that advertises new commands gets a working UI for free.
 */
function InvokeForm({
  capabilities,
  invoke,
}: {
  capabilities: NodeCapabilityInfo[];
  invoke: InvokeFn;
}): React.ReactElement {
  const [command, setCommand] = useState(capabilities[0]?.name ?? '');
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<{ ok: boolean; text: string } | null>(null);

  const selected = useMemo(
    () => capabilities.find((c) => c.name === command) ?? null,
    [capabilities, command]
  );
  const fields = useMemo(
    () => Object.entries(selected?.params_schema ?? {}),
    [selected]
  );

  const run = async () => {
    if (!command) return;
    setBusy(true);
    setOutcome(null);
    try {
      // Coerce by the declared type so an int field doesn't arrive as a string.
      const params: Record<string, unknown> = {};
      for (const [name, type] of fields) {
        const raw = values[`${command}:${name}`] ?? '';
        if (raw === '') continue;
        const t = String(type).toLowerCase();
        params[name] =
          t.startsWith('int') ? Number.parseInt(raw, 10)
          : t.startsWith('float') || t.startsWith('number') ? Number.parseFloat(raw)
          : t.startsWith('bool') ? raw === 'true'
          : raw;
      }
      const res = await invoke(command, params);
      setOutcome(
        res.success
          ? { ok: true, text: JSON.stringify(res.result ?? null) }
          : { ok: false, text: res.error || 'The device reported a failure.' }
      );
    } catch (e) {
      setOutcome({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="grid items-start gap-2 sm:grid-cols-[minmax(11rem,0.8fr)_minmax(0,2fr)_auto]">
        <BrutalSelect
          value={command}
          disabled={busy}
          onChange={(v) => {
            setCommand(v);
            setOutcome(null);
          }}
          options={capabilities.map((cap) => ({
            value: cap.name,
            label: cap.node ? `${cap.name} · ${cap.node}` : cap.name,
          }))}
          hideChevron={capabilities.length <= 1}
          className="min-w-0"
        />

        <div className="grid min-w-0 gap-2 [grid-template-columns:repeat(auto-fit,minmax(min(100%,12rem),1fr))]">
          {fields.map(([name, type]) => (
            <input
              key={`${command}:${name}`}
              className="min-w-0 border-2 border-brutal-black bg-white px-3 py-2 text-sm dark:bg-zinc-900"
              placeholder={`${name} (${type})`}
              value={values[`${command}:${name}`] ?? ''}
              disabled={busy}
              onChange={(e) =>
                setValues((v) => ({ ...v, [`${command}:${name}`]: e.target.value }))
              }
              onKeyDown={(e) => {
                if (e.key === 'Enter') run();
              }}
            />
          ))}
        </div>

        <SettingsListAction className="h-10" tone="blue" disabled={busy} onClick={run}>
          {busy ? 'Running…' : 'Run'}
        </SettingsListAction>
      </div>

      {selected?.description && (
        <p className="text-xs text-neutral-500">{selected.description}</p>
      )}

      {outcome && (
        <pre
          className={`text-[11px] overflow-x-auto border-2 p-2 ${
            outcome.ok
              ? 'border-brutal-green bg-green-50 dark:bg-green-900/20'
              : 'border-brutal-red bg-red-50 dark:bg-red-900/20'
          }`}
        >
          {outcome.text}
        </pre>
      )}
    </div>
  );
}

/** Invoke a capability on a directly-connected node (phone, TV, bridge). */
export function NodeInvokePanel({
  nodeId,
  capabilities,
}: {
  nodeId: string;
  capabilities: NodeCapabilityInfo[];
}): React.ReactElement {
  if (!capabilities.length) {
    return (
      <p className="text-xs text-neutral-500">
        This device advertises no capabilities to invoke.
      </p>
    );
  }
  return (
    <InvokeForm
      capabilities={capabilities}
      invoke={(command, params) => invokeNode(nodeId, command, params)}
    />
  );
}

/**
 * Invoke a capability belonging to a Suzent peer's own devices.
 *
 * Loaded on demand rather than on the polling loop: reading a peer's
 * capabilities is a live network call to that machine, so doing it every few
 * seconds for every peer would hammer the mesh for data nobody is looking at.
 */
export function PeerInvokePanel({ peerId }: { peerId: string }): React.ReactElement {
  const [capabilities, setCapabilities] = useState<NodeCapabilityInfo[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);

  // Deps are only the things that should *start* a new fetch. Including state
  // this effect writes (loading/capabilities) would re-run it mid-flight, and
  // the previous run's cleanup would flip `cancelled` and strand the panel on
  // "Reading capabilities…" forever.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPeerCapabilities(peerId)
      .then((caps) => {
        if (!cancelled) setCapabilities(caps);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, peerId, attempt]);

  if (!open) {
    return (
      <SettingsListAction onClick={() => setOpen(true)}>
        Show this device&rsquo;s capabilities
      </SettingsListAction>
    );
  }

  if (loading) {
    return <p className="text-xs text-neutral-500">Reading capabilities…</p>;
  }

  if (error) {
    return (
      <div className="space-y-1">
        <p className="text-xs text-brutal-red">{error}</p>
        <SettingsListAction onClick={() => setAttempt((n) => n + 1)}>
          Retry
        </SettingsListAction>
      </div>
    );
  }

  if (!capabilities?.length) {
    return (
      <p className="text-xs text-neutral-500">
        This device has no hardware capabilities attached.
      </p>
    );
  }

  return (
    <InvokeForm
      capabilities={capabilities}
      invoke={(command, params) => invokePeerCapability(peerId, command, params)}
    />
  );
}
