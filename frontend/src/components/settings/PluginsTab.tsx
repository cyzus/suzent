import React, { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { fetchPlugins, setPluginInstalled } from '../../lib/api';
import type { PluginInfo } from '../../lib/api';
import { RefreshButton } from '../RefreshButton';
import {
  Badge,
  SectionCardHeader,
  SettingsCard,
  SettingsHelp,
  SettingsListAction,
  SettingsListItem,
  SettingsPage,
} from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

function StatusBadge({
  plugin,
  t,
}: {
  plugin: PluginInfo;
  t: (key: string) => string;
}): React.ReactElement {
  if (plugin.status === 'error')
    return <Badge tone="red">{t('settings.plugins.statusError')}</Badge>;
  if (!plugin.enabled) return <Badge tone="neutral">{t('settings.plugins.statusOff')}</Badge>;
  if (plugin.missing.length > 0)
    return <Badge tone="amber">{t('settings.plugins.statusMissing')}</Badge>;
  if (plugin.restartRequired)
    return <Badge tone="amber">{t('settings.plugins.statusRestart')}</Badge>;
  return <Badge tone="green">{t('settings.plugins.statusOn')}</Badge>;
}

export function PluginsTab(): React.ReactElement {
  const { t } = useI18n();
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      setPlugins(await fetchPlugins());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (plugin: PluginInfo): Promise<void> => {
    const installing = !plugin.enabled || plugin.missing.length > 0;
    if (installing && plugin.hasCode && plugin.source !== 'builtin') {
      if (!window.confirm(t('settings.plugins.confirmThirdParty'))) return;
    }
    setBusy(plugin.id);
    setError(null);
    try {
      const updated = await setPluginInstalled(plugin.id, installing);
      setPlugins((previous) => previous.map((p) => (p.id === updated.id ? updated : p)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await load();
    } finally {
      setBusy(null);
    }
  };

  return (
    <SettingsPage>
      <SettingsHeader
        title={t('settings.plugins.title')}
        subtitle={t('settings.plugins.subtitle')}
      />
      <SettingsCard className="space-y-3">
        <SectionCardHeader
          title={t('settings.plugins.listTitle')}
          description={t('settings.plugins.listDesc')}
          actions={
            <RefreshButton
              spinning={loading}
              disabled={loading || busy !== null}
              onClick={() => void load()}
            />
          }
        />
        {error && (
          <p
            role="alert"
            className="whitespace-pre-wrap rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
          >
            {error}
          </p>
        )}
        <SettingsHelp title={t('settings.plugins.helpTitle')}>
          <p>{t('settings.plugins.helpPackages')}</p>
          <p>{t('settings.plugins.helpCode')}</p>
        </SettingsHelp>

        {loading && plugins.length === 0 ? (
          <div className="p-8 text-center font-bold uppercase text-neutral-500 dark:text-neutral-400">
            {t('common.loading')}
          </div>
        ) : plugins.length === 0 ? (
          <div className="py-8 text-center font-bold uppercase text-neutral-600 dark:text-neutral-300">
            {t('settings.plugins.empty')}
          </div>
        ) : (
          <div className="space-y-3">
            {plugins.map((plugin) => (
              <SettingsListItem key={plugin.id}>
                <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-black">{plugin.name}</span>
                      <StatusBadge plugin={plugin} t={t} />
                      {plugin.source === 'builtin' && (
                        <Badge tone="blue">{t('settings.plugins.builtin')}</Badge>
                      )}
                    </div>
                    {plugin.description && (
                      <p className="text-sm text-neutral-600 dark:text-neutral-400">
                        {plugin.description}
                      </p>
                    )}
                    {plugin.error && (
                      <p className="text-xs text-red-700 dark:text-red-300">{plugin.error}</p>
                    )}
                    {plugin.missing.length > 0 && (
                      <p className="text-xs text-amber-700 dark:text-amber-300">
                        {t('settings.plugins.missing')} {plugin.missing.join(', ')}
                      </p>
                    )}
                    {plugin.enabled && plugin.restartRequired && (
                      <p className="text-xs text-amber-700 dark:text-amber-300">
                        {t('settings.plugins.restartHint')}
                      </p>
                    )}
                  </div>
                  <SettingsListAction
                    tone={plugin.enabled ? 'red' : 'blue'}
                    disabled={busy !== null || plugin.status === 'error'}
                    onClick={() => void toggle(plugin)}
                  >
                    {busy === plugin.id
                      ? t('settings.plugins.working')
                      : plugin.enabled && plugin.missing.length > 0
                        ? t('settings.plugins.retry')
                        : plugin.enabled
                          ? t('settings.plugins.remove')
                          : t('settings.plugins.install')}
                  </SettingsListAction>
                </div>
              </SettingsListItem>
            ))}
          </div>
        )}
      </SettingsCard>
    </SettingsPage>
  );
}
