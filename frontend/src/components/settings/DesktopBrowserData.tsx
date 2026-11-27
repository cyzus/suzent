import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import { desktopShell, invoke } from '../../lib/desktop';
import { BrutalButton } from '../BrutalButton';

interface DesktopBrowserDataProps {
  keep: boolean;
  disabled: boolean;
  onKeepChange: (keep: boolean) => void;
}

/** Whether the built-in browser keeps sign-ins, and a way to forget them. */
export function DesktopBrowserData({
  keep,
  disabled,
  onKeepChange,
}: DesktopBrowserDataProps): React.ReactElement {
  const { t } = useI18n();
  const [clearing, setClearing] = useState(false);
  const [result, setResult] = useState<'cleared' | 'clearError' | null>(null);

  const clear = async (): Promise<void> => {
    setClearing(true);
    setResult(null);
    try {
      await invoke('agent_browser_clear_data');
      setResult('cleared');
    } catch {
      setResult('clearError');
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <label className="flex items-center gap-3 font-bold">
          <input
            type="checkbox"
            className="h-5 w-5 accent-black"
            checked={keep}
            disabled={disabled}
            onChange={(event) => onKeepChange(event.target.checked)}
          />
          {t('settings.browser.desktopPersistent')}
        </label>
        <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
          {t('settings.browser.desktopPersistentHelp')}
        </p>
      </div>
      {desktopShell() === 'electron' && (
        <div>
          <BrutalButton size="sm" disabled={clearing} onClick={() => void clear()}>
            {t('settings.browser.clearData')}
          </BrutalButton>
          <p className="mt-2 text-sm text-neutral-500 dark:text-neutral-400">
            {t('settings.browser.clearDataHelp')}
          </p>
          {result && (
            <p role="status" className="mt-1 text-sm font-bold">
              {t(`settings.browser.${result}`)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
