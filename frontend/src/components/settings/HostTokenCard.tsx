import React, { useCallback, useEffect, useState } from 'react';
import {
  createHostToken,
  fetchApprovedDevices,
  revokeDevice,
  type ApprovedDevice,
} from '../../lib/api';
import { BrutalButton } from '../BrutalButton';
import { CopyButton } from './CopyButton';
import { SettingsCard, SectionCardHeader, SettingsListAction } from './SettingsCard';
import { relativeTime } from '../../lib/chatUtils';

/**
 * Host-token management: mint, list, revoke full-scope credentials.
 *
 * Self-contained: fetches its own device list filtered to scope=full, so it
 * can live in SecurityTab without threading state from DevicesTab.
 */
export function HostTokenCard(): React.ReactElement {
  const [minted, setMinted] = useState<string | null>(null);
  const [tokens, setTokens] = useState<ApprovedDevice[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const all = await fetchApprovedDevices();
      setTokens(all.filter((d) => d.scope === 'full'));
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const mint = useCallback(async () => {
    setBusy('mint');
    setError(null);
    try {
      const { token } = await createHostToken('Host access');
      setMinted(token);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }, [refresh]);

  const revoke = useCallback(
    async (deviceId: string) => {
      setBusy(deviceId);
      setError(null);
      try {
        await revokeDevice(deviceId);
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(null);
      }
    },
    [refresh]
  );

  return (
    <SettingsCard>
      <SectionCardHeader
        iconTone="black"
        icon={
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 013 3m3 0a6 6 0 01-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1121.75 8.25z" />
          </svg>
        }
        title="Host tokens"
        description="Full-access credentials for remote administration. Treat these like root passwords."
        actions={
          <BrutalButton disabled={busy === 'mint'} onClick={mint}>
            Create token
          </BrutalButton>
        }
      />

      {error && (
        <div className="border-2 border-brutal-red bg-red-50 dark:bg-red-900/20 text-brutal-red px-3 py-2 text-xs font-mono mb-3">
          {error}
        </div>
      )}

      {minted && (
        <div className="border-2 border-brutal-red px-3 py-2 space-y-1 mb-3">
          <div className="text-[11px] font-bold uppercase text-brutal-red">
            Copy now — shown once
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-xs break-all">{minted}</code>
            <CopyButton value={minted} tone="red" />
            <SettingsListAction onClick={() => setMinted(null)}>Dismiss</SettingsListAction>
          </div>
        </div>
      )}

      {tokens.length > 0 ? (
        <div className="space-y-2">
          {tokens.map((t) => (
            <div
              key={t.device_id}
              className="flex items-center justify-between gap-3 px-3 py-2 border-2 border-brutal-black/15 dark:border-white/10"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={`w-2.5 h-2.5 border border-brutal-black shrink-0 ${
                    t.connected ? 'bg-brutal-green' : 'bg-neutral-300 dark:bg-zinc-600'
                  }`}
                />
                <span className="font-bold text-sm truncate">{t.display_name}</span>
                {t.token_hint && (
                  <code className="text-[11px] text-neutral-500">{t.token_hint}</code>
                )}
                {t.approved_at && (
                  <span className="text-[11px] text-neutral-500">
                    {relativeTime(t.approved_at)}
                  </span>
                )}
              </div>
              <SettingsListAction
                tone="red"
                disabled={busy === t.device_id}
                onClick={() => revoke(t.device_id)}
              >
                Revoke
              </SettingsListAction>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-neutral-500">
          No host tokens issued. These grant full remote access — only create one
          when you need to administer this device from another machine.
        </p>
      )}
    </SettingsCard>
  );
}
