import React, { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { decideAcpPairing, fetchAcpPairing, revokeAcpGrant } from '../../lib/acpPairing';
import type { AcpPairingStatus } from '../../lib/acpPairing';
import { SettingsListAction, SettingsListItem } from './SettingsCard';

export function AcpConnections(): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<AcpPairingStatus>({ pending: [], grants: [] });
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => setStatus(await fetchAcpPairing()), []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const next = await fetchAcpPairing();
        if (!cancelled) setStatus(next);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const act = async (action: () => Promise<unknown>): Promise<void> => {
    setBusy(true);
    setError('');
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-3">
      <h3 className="font-black text-lg">{t('settings.acp.connectionsTitle')}</h3>
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        {t('settings.acp.connectionsScope')}
      </p>
      <p className="text-xs text-neutral-500">{t('settings.acp.connectionsHint')}</p>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {loading && <p>{t('common.loading')}</p>}
      {!loading && !status.pending.length && !status.grants.length && (
        <p className="text-sm">{t('settings.acp.connectionsEmpty')}</p>
      )}
      {status.pending.map((item) => (
        <SettingsListItem key={item.request_id}>
          <div className="p-4 space-y-3">
            <p className="font-bold break-words">{item.client_name}</p>
            <p>
              {t('settings.acp.pairingCode')}: <code className="font-bold">{item.code}</code>
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!confirmed[item.request_id]}
                onChange={(e) =>
                  setConfirmed((previous) => ({ ...previous, [item.request_id]: e.target.checked }))
                }
              />
              {t('settings.acp.confirmCode')}
            </label>
            <div className="flex gap-2">
              <SettingsListAction
                disabled={busy || !confirmed[item.request_id]}
                onClick={() => void act(() => decideAcpPairing(item.request_id, true))}
              >
                {t('settings.acp.approveConnection')}
              </SettingsListAction>
              <SettingsListAction
                disabled={busy}
                onClick={() => void act(() => decideAcpPairing(item.request_id, false))}
              >
                {t('settings.acp.declineConnection')}
              </SettingsListAction>
            </div>
          </div>
        </SettingsListItem>
      ))}
      {status.grants.map((grant) => (
        <SettingsListItem key={grant.grant_id}>
          <div className="p-4 flex items-center justify-between gap-3">
            <span className="font-bold break-words">{grant.client_name}</span>
            <SettingsListAction
              disabled={busy}
              onClick={() => void act(() => revokeAcpGrant(grant.grant_id))}
            >
              {t('settings.acp.revokeConnection')}
            </SettingsListAction>
          </div>
        </SettingsListItem>
      ))}
    </section>
  );
}
