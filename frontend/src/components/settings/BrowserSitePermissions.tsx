import React, { useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  fetchSiteRules,
  removeSiteRule,
  saveSiteRule,
  siteOrigin,
  type SiteRule,
} from '../../lib/browserSites';
import { BrutalButton } from '../BrutalButton';
import { BrutalSelect } from '../BrutalSelect';
import { SectionCardHeader, SettingsCard } from './SettingsCard';

const INPUT_CLASS =
  'w-full min-w-0 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500';

/** Sites where the agent may, or may never, run its own code without asking. */
export function BrowserSitePermissions(): React.ReactElement {
  const { t } = useI18n();
  const [rules, setRules] = useState<SiteRule[] | null>(null);
  const [site, setSite] = useState('');
  const [behavior, setBehavior] = useState<SiteRule['behavior']>('allow');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (work: () => Promise<void>): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await work();
      setRules(await fetchSiteRules());
    } catch {
      setError(t('settings.browser.sites.error'));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void run(async () => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const origin = siteOrigin(site);

  const add = (event: React.FormEvent): void => {
    event.preventDefault();
    if (!origin || busy) return;
    void run(async () => {
      // One choice per site: a new one replaces the old.
      for (const rule of rules ?? []) {
        if (rule.site === origin) await removeSiteRule(rule.id);
      }
      await saveSiteRule(origin, behavior);
      setSite('');
    });
  };

  return (
    <SettingsCard className="space-y-3">
      <SectionCardHeader
        title={t('settings.browser.sites.title')}
        description={t('settings.browser.sites.description')}
      />
      {error && (
        <p role="alert" className="text-sm font-bold">
          {error}
        </p>
      )}
      {rules && rules.length === 0 && (
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          {t('settings.browser.sites.empty')}
        </p>
      )}
      {rules && rules.length > 0 && (
        <ul className="divide-y-2 divide-brutal-black/10 border-2 border-brutal-black dark:divide-white/10">
          {rules.map((rule) => (
            <li key={rule.id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate font-mono" title={rule.site}>
                {rule.site}
              </span>
              <span className="shrink-0 text-xs font-bold uppercase">
                {t(
                  rule.behavior === 'allow'
                    ? 'settings.browser.sites.allowed'
                    : 'settings.browser.sites.blocked'
                )}
              </span>
              <BrutalButton
                size="xs"
                disabled={busy}
                onClick={() => void run(() => removeSiteRule(rule.id))}
              >
                {t('settings.browser.sites.remove')}
              </BrutalButton>
            </li>
          ))}
        </ul>
      )}
      <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={add}>
        <label className="min-w-0 flex-1 text-xs font-bold">
          {t('settings.browser.sites.site')}
          <input
            className={`${INPUT_CLASS} mt-1`}
            value={site}
            placeholder="https://example.com"
            onChange={(event) => setSite(event.target.value)}
          />
        </label>
        <div className="sm:w-40">
          <BrutalSelect
            label={t('settings.browser.sites.choice')}
            value={behavior}
            onChange={(value) => setBehavior(value as SiteRule['behavior'])}
            options={[
              { value: 'allow', label: t('settings.browser.sites.allow') },
              { value: 'deny', label: t('settings.browser.sites.block') },
            ]}
          />
        </div>
        <BrutalButton type="submit" disabled={busy || !origin}>
          {t('settings.browser.sites.add')}
        </BrutalButton>
      </form>
    </SettingsCard>
  );
}
