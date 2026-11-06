import React, { useCallback, useEffect, useState } from 'react';
import { GlobeAltIcon } from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import { mobileRequest } from '../../lib/mobileApi';
import { BrutalButton, BrutalLink } from '../BrutalButton';
import { BrutalOnOff } from '../BrutalOnOff';
import { Badge, SectionCardHeader, SettingsCard } from './SettingsCard';

type RelayState = 'stopped' | 'connecting' | 'connected' | 'rejected' | 'replaced';

export interface RelayStatus {
  url: string | null;
  enabled: boolean;
  has_key: boolean;
  state: RelayState;
  detail: string | null;
  protocol: number | null;
}

const DEPLOY_DOCS = 'https://github.com/cyzus/suzent-relay#deploy';
const BADGE_TONE: Record<RelayState, 'green' | 'amber' | 'red' | 'neutral'> = {
  stopped: 'neutral',
  connecting: 'amber',
  connected: 'green',
  rejected: 'red',
  replaced: 'red',
};
const inputClass =
  'w-full border-2 border-brutal-black bg-white px-3 py-2 text-sm font-mono focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:bg-zinc-800 dark:text-white';

/** Settings → Devices: connect this Suzent to a relay the user deployed. */
export function RelayCard(): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<RelayStatus | null>(null);
  const [url, setUrl] = useState('');
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((next: RelayStatus) => {
    setStatus(next);
    setUrl((current) => current || next.url || '');
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = (): void => {
      mobileRequest<RelayStatus>('relay')
        .then((next) => {
          if (!cancelled) apply(next);
        })
        .catch(() => {});
    };
    poll();
    const timer = window.setInterval(poll, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [apply]);

  const save = useCallback(
    async (enabled: boolean, keyChange?: string) => {
      setBusy(true);
      setError(null);
      try {
        const next = await mobileRequest<RelayStatus>('relay', {
          url: url.trim() || null,
          key: keyChange ?? (key.trim() ? key.trim() : null),
          enabled,
        });
        setKey('');
        apply(next);
      } catch {
        setError(t('relay.invalidUrl'));
      } finally {
        setBusy(false);
      }
    },
    [apply, key, t, url]
  );

  const reset = useCallback(async () => {
    if (!window.confirm(t('relay.resetConfirm'))) return;
    setBusy(true);
    try {
      apply(await mobileRequest<RelayStatus>('relay/reset', {}));
    } finally {
      setBusy(false);
    }
  }, [apply, t]);

  const state = status?.state ?? 'stopped';
  const enabled = !!status?.enabled;

  return (
    <SettingsCard>
      <SectionCardHeader
        icon={<GlobeAltIcon className="w-5 h-5 stroke-2" />}
        iconTone="blue"
        title={t('relay.title')}
        description={t('relay.description')}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={BADGE_TONE[state]}>{t(`relay.state_${state}`)}</Badge>
            <BrutalOnOff
              checked={enabled}
              disabled={busy || (!enabled && !url.trim())}
              onChange={(next) => save(next)}
              aria-label={t('relay.title')}
            />
          </div>
        }
      />

      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          void save(enabled || !!url.trim());
        }}
      >
        <label className="block space-y-1">
          <span className="text-xs font-bold uppercase">{t('relay.url')}</span>
          <input
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://suzent-relay.example.workers.dev"
            className={inputClass}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-bold uppercase">{t('relay.key')}</span>
          <input
            type="password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            placeholder={status?.has_key ? t('relay.keySaved') : t('relay.keyPlaceholder')}
            className={inputClass}
            autoComplete="off"
          />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <BrutalButton type="submit" variant="primary" size="sm" disabled={busy || !url.trim()}>
            {busy ? t('relay.saving') : t('relay.save')}
          </BrutalButton>
          {status?.has_key && (
            <BrutalButton type="button" size="sm" disabled={busy} onClick={() => save(enabled, '')}>
              {t('relay.removeKey')}
            </BrutalButton>
          )}
          {status?.url && (
            <BrutalButton type="button" size="sm" disabled={busy} onClick={reset}>
              {t('relay.reset')}
            </BrutalButton>
          )}
          <BrutalLink href={DEPLOY_DOCS} target="_blank" rel="noreferrer noopener" size="sm">
            {t('relay.deployLink')}
          </BrutalLink>
        </div>
      </form>

      {error && (
        <p className="mt-3 border-2 border-brutal-red bg-red-50 px-3 py-2 text-xs text-brutal-red dark:bg-red-900/20">
          {error}
        </p>
      )}
      {state === 'rejected' && (
        <p className="mt-3 text-xs font-bold text-brutal-red">{t('relay.rejectedHint')}</p>
      )}
      {state === 'replaced' && (
        <p className="mt-3 text-xs font-bold text-brutal-red">{t('relay.replacedHint')}</p>
      )}
      {state === 'connecting' && status?.detail && (
        <p className="mt-3 text-xs font-mono text-neutral-500 dark:text-neutral-400">
          {status.detail}
        </p>
      )}

      <p className="mt-3 text-[11px] text-neutral-600 dark:text-neutral-300">
        {status?.url ? t('relay.webhooksNote') : t('relay.deployHint')}
      </p>
      <p className="mt-1 text-[11px] text-neutral-600 dark:text-neutral-300">
        {t('relay.backgroundHint')}
      </p>
    </SettingsCard>
  );
}
