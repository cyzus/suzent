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

  useEffect(() => {
    let active = true;
    const check = async (): Promise<void> => {
      try {
        const response = await fetch(`${getApiBase()}/browser/extension`);
        if (!response.ok) throw new Error();
        const result = await response.json();
        if (active) {
          setConnected(result.connected);
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
    <div className="space-y-3">
      <p role="status" className="font-bold">
        {t(`settings.browser.extension${connected ? 'Connected' : 'Disconnected'}`)}
      </p>
      <p className="text-sm">{t('settings.browser.extensionHelp')}</p>
      <ol className="list-decimal pl-5 text-sm space-y-2">
        <li>{t('settings.browser.extensionInstall')}</li>
        <li>{t('settings.browser.extensionPair')}</li>
      </ol>
      <div className="flex gap-2 flex-wrap">
        <BrutalButton disabled={busy} onClick={() => void action('download')}>
          {t('settings.browser.extensionDownload')}
        </BrutalButton>
        <BrutalButton disabled={busy} onClick={() => void action('pair')}>
          {t('settings.browser.extensionPairButton')}
        </BrutalButton>
        <BrutalButton disabled={busy} onClick={() => void action('revoke')}>
          {t('settings.browser.extensionRevoke')}
        </BrutalButton>
      </div>
      {pairUrl && (
        <div>
          <p className="text-sm">{t('settings.browser.extensionOtherBrowser')}</p>
          <input
            className="w-full p-2 border-2 border-black text-sm"
            aria-label={t('settings.browser.extensionPairButton')}
            readOnly
            value={pairUrl}
            onFocus={(event) => event.target.select()}
          />
        </div>
      )}
      {error && <p role="alert">{t('settings.browser.error')}</p>}
    </div>
  );
}
