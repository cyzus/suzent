import React, { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import {
  fetchBrowserSettings,
  browserChannelOptions,
  connectionModeChange,
  existingBrowserAvailable,
  saveBrowserSettings,
  type BrowserPreferences,
  type BrowserSettingsResponse,
} from '../../lib/browserSettings';
import { BrutalSelect } from '../BrutalSelect';
import { BrutalButton } from '../BrutalButton';
import { SettingsCard, SettingsPage } from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

export function BrowserTab(): React.ReactElement {
  const { t } = useI18n();
  const [data, setData] = useState<BrowserSettingsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [saved, setSaved] = useState(false);
  const saving = useRef(false);

  const load = async (): Promise<void> => {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError(false);
    try {
      setData(await fetchBrowserSettings());
    } catch {
      setError(true);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const update = async (change: Partial<BrowserPreferences>): Promise<void> => {
    if (!data || saving.current) return;
    saving.current = true;
    setBusy(true);
    setError(false);
    setSaved(false);
    try {
      setData(await saveBrowserSettings(change));
      setSaved(true);
    } catch {
      setError(true);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  };

  return (
    <SettingsPage>
      <SettingsHeader
        title={t('settings.browser.title')}
        subtitle={t('settings.browser.subtitle')}
        actions={
          <BrutalButton disabled={busy} onClick={() => void load()}>
            {t('settings.browser.recheck')}
          </BrutalButton>
        }
      />
      {error && <p role="alert">{t('settings.browser.error')}</p>}
      {!data ? (
        error ? (
          <BrutalButton onClick={() => void load()}>{t('settings.browser.retry')}</BrutalButton>
        ) : (
          <p>{t('settings.browser.loading')}</p>
        )
      ) : (
        <SettingsCard>
          <div className="space-y-6">
            <BrutalSelect
              label={t('settings.browser.connectionMode')}
              value={data.settings.connection_mode}
              disabled={busy || data.environment_overrides.includes('connection_mode')}
              onChange={(value) =>
                void update(
                  connectionModeChange(data, value as BrowserPreferences['connection_mode'])
                )
              }
              options={[
                { value: 'managed', label: t('settings.browser.managed') },
                {
                  value: 'existing',
                  label: t('settings.browser.existing'),
                  disabled: !existingBrowserAvailable(data),
                },
              ]}
            />
            {data.settings.connection_mode === 'existing' && (
              <p className="text-sm">{t('settings.browser.existingHelp')}</p>
            )}
            <div>
              <BrutalSelect
                label={t('settings.browser.channel')}
                value={data.settings.channel}
                disabled={busy || data.environment_overrides.includes('channel')}
                onChange={(channel) =>
                  void update({ channel: channel as BrowserPreferences['channel'] })
                }
                options={browserChannelOptions(data.available_browsers, t).map((option) => ({
                  ...option,
                  disabled:
                    option.disabled ||
                    (data.settings.connection_mode === 'existing' && option.value === 'chromium'),
                }))}
              />
              <p className="mt-2 text-sm text-neutral-500">{t('settings.browser.channelHelp')}</p>
              {!data.available_browsers[data.settings.channel] && (
                <p role="alert" className="mt-2 text-sm font-bold">
                  {t('settings.browser.selectedUnavailable')}
                </p>
              )}
            </div>
            <div>
              <label className="flex items-center gap-3 font-bold">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-black"
                  checked={data.settings.persistent}
                  disabled={
                    busy ||
                    data.settings.connection_mode === 'existing' ||
                    data.environment_overrides.includes('persistent')
                  }
                  onChange={(event) => void update({ persistent: event.target.checked })}
                />
                {t('settings.browser.persistent')}
              </label>
              <p className="mt-2 text-sm text-neutral-500">
                {t('settings.browser.persistentHelp')}
              </p>
            </div>
            <div>
              <label className="flex items-center gap-3 font-bold">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-black"
                  checked={!data.settings.headless}
                  disabled={
                    busy ||
                    data.settings.connection_mode === 'existing' ||
                    data.environment_overrides.includes('headless')
                  }
                  onChange={(event) => void update({ headless: !event.target.checked })}
                />
                {t('settings.browser.visible')}
              </label>
              <p className="mt-2 text-sm text-neutral-500">{t('settings.browser.visibleHelp')}</p>
            </div>
            {data.environment_overrides.length > 0 && (
              <p className="text-sm">{t('settings.browser.overrides')}</p>
            )}
            <p role="status" className="text-sm font-bold">
              {busy
                ? t('settings.browser.saving')
                : saved
                  ? t('settings.browser.saved')
                  : t('settings.browser.restart')}
            </p>
          </div>
        </SettingsCard>
      )}
    </SettingsPage>
  );
}
