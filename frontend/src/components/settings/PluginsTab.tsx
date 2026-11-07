import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowPathIcon,
  CameraIcon,
  ChatBubbleLeftRightIcon,
  EnvelopeIcon,
  MicrophoneIcon,
  PlusIcon,
  PuzzlePieceIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { useI18n } from '../../i18n';
import {
  connectPluginIntegration,
  disconnectPluginIntegration,
  fetchPlugins,
  installPluginBinary,
  setPluginInstalled,
} from '../../lib/api';
import type { PluginBinary, PluginInfo, PluginIntegration } from '../../lib/api';
import { RefreshButton } from '../RefreshButton';
import { MailAccounts } from './MailAccounts';
import {
  Badge,
  SectionCardHeader,
  SettingsCard,
  SettingsListAction,
  SettingsListItem,
  SettingsPage,
} from './SettingsCard';
import { SettingsHeader } from './SettingsHeader';

/** Plugins that ship no logo of their own. */
const FALLBACK_ICONS: Record<string, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  camera: CameraIcon,
  'wake-word': MicrophoneIcon,
  slack: ChatBubbleLeftRightIcon,
  feishu: ChatBubbleLeftRightIcon,
  email: EnvelopeIcon,
};

/** Settings a loaded plugin needs beyond install, programs and sign-in. */
const PLUGIN_SETTINGS: Record<string, React.ComponentType<{ openLink: (url: string) => void }>> = {
  email: MailAccounts,
};

function PluginIcon({ plugin }: { plugin: PluginInfo }): React.ReactElement {
  const Fallback = FALLBACK_ICONS[plugin.id] ?? PuzzlePieceIcon;
  return (
    <div
      aria-hidden="true"
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm border border-brutal-black/20 bg-white dark:border-white/10"
    >
      {plugin.icon ? (
        <img src={plugin.icon} alt="" className="h-6 w-6 object-contain" />
      ) : (
        <Fallback className="h-6 w-6 text-neutral-700" />
      )}
    </div>
  );
}

function PluginAction({
  plugin,
  busy,
  disabled,
  onClick,
  t,
  installLabel,
}: {
  plugin: PluginInfo;
  busy: boolean;
  disabled: boolean;
  onClick: () => void;
  t: (key: string) => string;
  installLabel: string;
}): React.ReactElement {
  const retry = plugin.enabled && plugin.missing.length > 0;
  const [Icon, label] = retry
    ? [ArrowPathIcon, t('settings.plugins.retry')]
    : plugin.enabled
      ? [TrashIcon, t('settings.plugins.remove')]
      : [PlusIcon, installLabel];
  const tone = plugin.enabled && !retry ? 'red' : 'blue';
  return (
    <SettingsListAction
      tone={tone}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex shrink-0 items-center gap-1.5 self-start ${
        tone === 'blue'
          ? '!border-brutal-blue !text-brutal-blue dark:!border-blue-400 dark:!text-blue-400'
          : ''
      }`}
    >
      {busy ? (
        <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      ) : (
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {busy ? t('settings.plugins.working') : label}
    </SettingsListAction>
  );
}

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

/** Plugins that connect a hosted service; listed on the Services page. */
type Translate = (key: string, params?: Record<string, unknown>) => string;

/** A program the plugin runs on this computer, downloaded only after a yes. */
export function BinaryRow({
  pluginId,
  binary,
  onChange,
  t,
}: {
  pluginId: string;
  binary: PluginBinary;
  onChange: () => Promise<void>;
  t: Translate;
}): React.ReactElement {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const params = {
    name: binary.name,
    version: binary.version,
    package: binary.package ?? binary.name,
  };

  const install = async (): Promise<void> => {
    const consent = [
      t('settings.plugins.confirmBinary', params),
      binary.notice,
      t('settings.plugins.confirmBinaryQuestion', params),
    ]
      .filter(Boolean)
      .join('\n\n');
    if (!window.confirm(consent)) return;
    setBusy(true);
    setError(null);
    try {
      await installPluginBinary(pluginId, binary.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      await onChange();
    }
  };

  return (
    <div className="space-y-2 border-t-2 border-dashed border-neutral-300 pt-3 dark:border-white/15">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-bold">{binary.name}</span>
          {binary.installed ? (
            <Badge tone="green">{t('settings.plugins.binaryReady', params)}</Badge>
          ) : (
            <Badge tone="amber">{t('settings.plugins.statusMissing')}</Badge>
          )}
        </div>
        {!binary.installed && binary.supported && (
          <SettingsListAction onClick={() => void install()} disabled={busy}>
            {busy ? t('settings.plugins.working') : t('settings.plugins.installBinary', params)}
          </SettingsListAction>
        )}
      </div>
      {binary.installed && binary.path && (
        <p className="break-all font-mono text-xs text-neutral-600 dark:text-neutral-400">
          {binary.path}
        </p>
      )}
      {!binary.installed && (
        <p className="text-xs text-neutral-600 dark:text-neutral-400">
          {binary.supported
            ? t('settings.plugins.binaryMissing', params)
            : t('settings.plugins.binaryUnsupported', params)}
        </p>
      )}
      {error && <p className="text-xs text-red-700 dark:text-red-300">{error}</p>}
    </div>
  );
}

export function isServicePlugin(plugin: PluginInfo): boolean {
  return plugin.category === 'service';
}

interface PluginsTabProps {
  /**
   * `services`: the hosted services, for the Services page. `extensions`:
   * everything else except chat apps, which the chat apps page installs.
   */
  scope?: 'extensions' | 'services';
  /** Render only the list card, inside another page. */
  embedded?: boolean;
  /** Called after a plugin is turned on or off, so tool lists can reload. */
  onPluginsChanged?: () => Promise<void> | void;
}

export function PluginsTab({
  scope = 'extensions',
  embedded = false,
  onPluginsChanged,
}: PluginsTabProps): React.ReactElement {
  const { t } = useI18n();
  const prefix = scope === 'services' ? 'settings.services' : 'settings.plugins';
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
      await onPluginsChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      await load();
    } finally {
      setBusy(null);
    }
  };

  const shown = plugins.filter((plugin) =>
    scope === 'services' ? isServicePlugin(plugin) : !isServicePlugin(plugin) && !plugin.channel
  );

  const card = (
    <SettingsCard className="space-y-3">
      <SectionCardHeader
        title={t(`${prefix}.listTitle`)}
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
      <p className="text-xs text-neutral-600 dark:text-neutral-400">{t(`${prefix}.helpCode`)}</p>

      {loading && plugins.length === 0 ? (
        <div className="p-8 text-center font-bold uppercase text-neutral-500 dark:text-neutral-400">
          {t('common.loading')}
        </div>
      ) : shown.length === 0 ? (
        <div className="py-8 text-center font-bold uppercase text-neutral-600 dark:text-neutral-300">
          {t(`${prefix}.empty`)}
        </div>
      ) : (
        <div className="space-y-3">
          {shown.map((plugin) => (
            <SettingsListItem key={plugin.id}>
              <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 flex-1 gap-3">
                  <PluginIcon plugin={plugin} />
                  <div className="min-w-0 flex-1 space-y-1">
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
                      plugin.binaries?.map((binary) => (
                        <BinaryRow
                          key={binary.name}
                          pluginId={plugin.id}
                          binary={binary}
                          onChange={refresh}
                          t={t}
                        />
                      ))}
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
                    {plugin.status === 'loaded' &&
                      (plugin.binaries ?? []).every((binary) => binary.installed) &&
                      PLUGIN_SETTINGS[plugin.id] &&
                      React.createElement(PLUGIN_SETTINGS[plugin.id], {
                        openLink: (url: string) => void openExternal(url, null),
                      })}
                  </div>
                </div>
                <PluginAction
                  plugin={plugin}
                  busy={busy === plugin.id}
                  disabled={busy !== null || plugin.status === 'error'}
                  onClick={() => void toggle(plugin)}
                  t={t}
                  installLabel={t(`${prefix}.install`)}
                />
              </div>
            </SettingsListItem>
          ))}
        </div>
      )}
    </SettingsCard>
  );

  if (embedded) return card;
  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.plugins.title')} />
      {card}
    </SettingsPage>
  );
}
