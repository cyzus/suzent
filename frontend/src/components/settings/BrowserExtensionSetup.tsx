import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import { getApiBase } from '../../lib/api';
import { BrutalButton } from '../BrutalButton';

export function BrowserExtensionSetup(): React.ReactElement {
  const { t } = useI18n();
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pairUrl, setPairUrl] = useState('');
  const [sourceDir, setSourceDir] = useState('');

  useEffect(() => {
    let active = true;
    const check = async (): Promise<void> => {
      try {
        const response = await fetch(`${getApiBase()}/browser/extension`);
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (active) {
          setConnected(result.connected);
          setSourceDir(result.source_dir ?? '');
          if (result.connected) setPairUrl('');
        }
      } catch {
        if (active) setConnected(false);
      }
    };
    void check();
    const timer = setInterval(() => void check(), 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const openExternal = async (url: string): Promise<void> => {
    if (window.__TAURI__) {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(url);
    } else window.open(url, '_blank', 'noopener,noreferrer');
  };

  const action = async (kind: 'download' | 'pair' | 'revoke'): Promise<void> => {
    setBusy(true);
    setError(false);
    try {
      if (kind === 'download') await openExternal(`${getApiBase()}/browser/extension/download`);
      else {
        const response = await fetch(`${getApiBase()}/browser/extension`, {
          method: kind === 'pair' ? 'POST' : 'DELETE',
          headers: { 'X-Suzent-Browser-Setup': '1' },
        });
        if (!response.ok) throw new Error();
        if (kind === 'pair') {
          const { url } = await response.json();
          setPairUrl(url);
          await openExternal(url);
        } else {
          setConnected(false);
          setPairUrl('');
        }
      }
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-2 border-brutal-black bg-neutral-50 p-3 dark:bg-zinc-900">
        <div className="flex items-center gap-3" role="status">
          <span
            aria-hidden="true"
            className={`h-3 w-3 shrink-0 border-2 border-brutal-black ${connected ? 'bg-brutal-green' : 'bg-brutal-yellow'}`}
          />
          <span className="text-sm font-bold">
            {t(`settings.browser.extension${connected ? 'Connected' : 'Disconnected'}`)}
          </span>
        </div>
        {connected && (
          <BrutalButton size="sm" disabled={busy} onClick={() => void action('revoke')}>
            {t('settings.browser.extensionRevoke')}
          </BrutalButton>
        )}
      </div>
      {connected ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          {t('settings.browser.extensionReady')}
        </p>
      ) : (
        <ol className="grid gap-4 sm:grid-cols-2">
          <li className="min-w-0 space-y-3 border-2 border-brutal-black p-4">
            <h3 className="flex items-center gap-2 font-bold">
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center bg-brutal-yellow text-xs font-mono text-brutal-black"
              >
                1
              </span>
              {t('settings.browser.extensionInstallTitle')}
            </h3>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
              {t('settings.browser.extensionInstall')}
            </p>
            {sourceDir && (
              <input
                className="w-full min-w-0 border-2 border-brutal-black bg-neutral-50 p-2 font-mono text-xs dark:bg-zinc-900"
                aria-label={t('settings.browser.extensionSource')}
                title={sourceDir}
                readOnly
                value={sourceDir}
                onFocus={(event) => event.target.select()}
              />
            )}
          </li>
          <li className="min-w-0 space-y-3 border-2 border-brutal-black p-4">
            <h3 className="flex items-center gap-2 font-bold">
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center bg-brutal-yellow text-xs font-mono text-brutal-black"
              >
                2
              </span>
              {t('settings.browser.extensionPairTitle')}
            </h3>
            <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
              {t('settings.browser.extensionPair')}
            </p>
            <BrutalButton variant="primary" disabled={busy} onClick={() => void action('pair')}>
              {t('settings.browser.extensionPairButton')}
            </BrutalButton>
          </li>
        </ol>
      )}
      {pairUrl && (
        <div className="space-y-2">
          <p className="text-xs text-neutral-600 dark:text-neutral-400">
            {t('settings.browser.extensionOtherBrowser')}
          </p>
          <input
            className="w-full border-2 border-brutal-black bg-neutral-50 p-2 font-mono text-xs dark:bg-zinc-900"
            aria-label={t('settings.browser.extensionPairButton')}
            readOnly
            value={pairUrl}
            onFocus={(event) => event.target.select()}
          />
        </div>
      )}
      <details className="border-t-2 border-brutal-black pt-3 text-sm">
        <summary className="cursor-pointer font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue">
          {t('settings.browser.extensionDetails')}
        </summary>
        <div className="mt-3 space-y-3 text-neutral-600 dark:text-neutral-400">
          <p>{t('settings.browser.extensionHelp')}</p>
          <p>{t('settings.browser.extensionDownloadHelp')}</p>
          <div className="flex flex-wrap gap-2">
            <BrutalButton size="sm" disabled={busy} onClick={() => void action('download')}>
              {t('settings.browser.extensionDownload')}
            </BrutalButton>
            {!connected && (
              <BrutalButton size="sm" disabled={busy} onClick={() => void action('revoke')}>
                {t('settings.browser.extensionRevoke')}
              </BrutalButton>
            )}
          </div>
        </div>
      </details>
      {error && (
        <p role="alert" className="text-sm font-bold">
          {t('settings.browser.error')}
        </p>
      )}
    </div>
  );
}
