import React, { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import {
  connectPluginIntegration,
  disconnectPluginIntegration,
  fetchPlugins,
  setPluginInstalled,
} from '../../lib/api';
import type { PluginInfo, PluginIntegration } from '../../lib/api';
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

const INPUT_CLASS =
  'w-full min-w-0 bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white dark:placeholder-neutral-500';

async function openExternal(url: string, popup: Window | null): Promise<void> {
  if (window.__TAURI__) {
    popup?.close();
    const { open } = await import('@tauri-apps/plugin-shell');
    await open(url);
  } else if (popup) popup.location.href = url;
  else window.open(url, '_blank', 'noopener,noreferrer');
}

/** Sign-in, or token entry, for one service a plugin connects. */
export function IntegrationRow({
  pluginId,
  integration,
  onChange,
  t,
}: {
  pluginId: string;
  integration: PluginIntegration;
  onChange: () => Promise<void>;
  t: (key: string) => string;
}): React.ReactElement {
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const waiting = integration.signIn?.state === 'waiting';

  // While the browser sign-in is open, poll until it finishes.
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => void onChange(), 2000);
    return () => window.clearInterval(timer);
  }, [waiting, onChange]);

  const run = async (action: () => Promise<void>): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      await onChange();
    }
  };

  const signIn = (): Promise<void> =>
    run(async () => {
      // Opened before the request so the browser treats it as the click's popup.
      const popup = window.__TAURI__ ? null : window.open('', '_blank');
      // The sign-in page must not be able to steer this window.
      if (popup) popup.opener = null;
      try {
        const result = await connectPluginIntegration(pluginId, integration.id);
        if (result.authorizeUrl) await openExternal(result.authorizeUrl, popup);
        else popup?.close();
      } catch (err) {
        popup?.close();
        throw err;
      }
    });

  const saveToken = (): Promise<void> =>
    run(async () => {
      await connectPluginIntegration(pluginId, integration.id, token.trim());
      setToken('');
    });

  const disconnect = (): Promise<void> =>
    run(async () => {
      await disconnectPluginIntegration(pluginId, integration.id);
    });

  const problem = error || integration.error || integration.signIn?.error;

  return (
    <div className="space-y-2 border-t-2 border-dashed border-neutral-300 pt-3 dark:border-white/15">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold">{integration.name}</span>
          {integration.connected ? (
            <Badge tone={integration.error ? 'amber' : 'green'}>
              {t('settings.plugins.connected')}
            </Badge>
          ) : (
            <Badge tone="neutral">{t('settings.plugins.notConnected')}</Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {integration.auth === 'oauth' && (!integration.connected || integration.error) && (
            <SettingsListAction
              tone="blue"
              disabled={busy || waiting}
              onClick={() => void signIn()}
            >
              {busy || waiting
                ? t('settings.plugins.working')
                : integration.connected
                  ? t('settings.plugins.reconnect')
                  : t('settings.plugins.connect')}
            </SettingsListAction>
          )}
          {integration.connected && (
            <SettingsListAction tone="red" disabled={busy} onClick={() => void disconnect()}>
              {t('settings.plugins.disconnect')}
            </SettingsListAction>
          )}
        </div>
      </div>
      {integration.auth === 'token' && !integration.connected && (
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            if (token.trim()) void saveToken();
          }}
        >
          <input
            type="password"
            autoComplete="off"
            aria-label={t('settings.plugins.tokenPlaceholder')}
            placeholder={t('settings.plugins.tokenPlaceholder')}
            value={token}
            onChange={(event) => setToken(event.target.value)}
            className={INPUT_CLASS}
          />
          <SettingsListAction tone="blue" type="submit" disabled={busy || !token.trim()}>
            {busy ? t('settings.plugins.working') : t('settings.plugins.saveToken')}
          </SettingsListAction>
        </form>
      )}
      {waiting && (
        <p className="text-xs text-blue-700 dark:text-blue-300">
          {t('settings.plugins.waitingForBrowser')}
        </p>
      )}
      {problem && !waiting && (
        <p role="alert" className="text-xs text-red-700 dark:text-red-300">
          {problem}
        </p>
      )}
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        {integration.auth === 'token' ? (
          <>
            {t('settings.plugins.tokenHint')}{' '}
            {integration.tokenHelpUrl && (
              <button
                type="button"
                className="underline"
                onClick={() => void openExternal(integration.tokenHelpUrl as string, null)}
              >
                {t('settings.plugins.createToken')}
              </button>
            )}
          </>
        ) : (
          t('settings.plugins.signInHint')
        )}
      </p>
    </div>
  );
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

  // A quiet reload, for sign-in progress, that keeps the list on screen.
  const refresh = useCallback(async (): Promise<void> => {
    try {
      setPlugins(await fetchPlugins());
    } catch {
      // The next poll or a manual refresh retries.
    }
  }, []);

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
                    {plugin.enabled &&
                      plugin.integrations?.map((integration) => (
                        <IntegrationRow
                          key={integration.id}
                          pluginId={plugin.id}
                          integration={integration}
                          onChange={refresh}
                          t={t}
                        />
                      ))}
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
