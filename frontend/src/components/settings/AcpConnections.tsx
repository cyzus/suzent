import React, { useCallback, useEffect, useState } from 'react';
import { BrutalButton } from '../BrutalButton';
import { useI18n } from '../../i18n';
import { decideAcpPairing, fetchAcpPairing, revokeAcpGrant } from '../../lib/acpPairing';
import type { AcpPairingStatus } from '../../lib/acpPairing';
import { SectionCardHeader, SettingsCard, SettingsHelp, SettingsListItem } from './SettingsCard';

export function AcpConnections(): React.ReactElement {
  const { t, locale } = useI18n();
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
    <SettingsCard className="space-y-3">
      <SectionCardHeader
        title={t('settings.acp.connectionsTitle')}
        description={t('settings.acp.connectionsDesc')}
      />
      <SettingsHelp title={t('settings.acp.connectEditor')}>
        <p>{t('settings.acp.editorSetup')}</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt>{t('settings.acp.command')}</dt>
          <dd>
            <code>suzent</code>
          </dd>
          <dt>{t('settings.acp.arguments')}</dt>
          <dd>
            <code>acp</code>
          </dd>
        </dl>
        <p>{t('settings.acp.connectionsHint')}</p>
        <p>{t('settings.acp.stdioHint')}</p>
        <p>{t('settings.acp.connectionsScope')}</p>
      </SettingsHelp>
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
            <p className="text-xs font-bold text-amber-700 dark:text-amber-400">
              {t('settings.acp.pendingApproval')}
            </p>
            <p className="font-bold break-words">{item.client_name}</p>
            <p>
              {t('settings.acp.pairingCode')}: <code className="font-bold">{item.code}</code>
            </p>
            <p className="text-xs text-neutral-600 dark:text-neutral-300">
              {t('settings.acp.approvalScope')}
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
            <div className="flex flex-wrap gap-2">
              <BrutalButton
                size="sm"
                variant="primary"
                disabled={busy || !confirmed[item.request_id]}
                onClick={() => void act(() => decideAcpPairing(item.request_id, true))}
              >
                {t('settings.acp.approveConnection')}
              </BrutalButton>
              <BrutalButton
                size="sm"
                disabled={busy}
                onClick={() => void act(() => decideAcpPairing(item.request_id, false))}
              >
                {t('settings.acp.declineConnection')}
              </BrutalButton>
            </div>
          </div>
        </SettingsListItem>
      ))}
      {status.grants.map((grant) => (
        <SettingsListItem key={grant.grant_id}>
          <div className="p-4 flex items-center justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="font-bold break-words">{grant.client_name}</p>
              <p className="text-xs text-neutral-600 dark:text-neutral-300">
                {t('settings.acp.approvedAt')}{' '}
                <time dateTime={new Date(grant.approved_at * 1000).toISOString()}>
                  {new Date(grant.approved_at * 1000).toLocaleString(locale)}
                </time>
              </p>
              <p className="text-xs text-neutral-600 dark:text-neutral-300 break-all">
                {t('settings.acp.grantId')}: <code>{grant.grant_id}</code>
              </p>
            </div>
            <BrutalButton
              size="sm"
              disabled={busy}
              className="shrink-0 whitespace-nowrap"
              onClick={() => void act(() => revokeAcpGrant(grant.grant_id))}
            >
              {t('settings.acp.revokeConnection')}
            </BrutalButton>
          </div>
        </SettingsListItem>
      ))}
    </SettingsCard>
  );
}
