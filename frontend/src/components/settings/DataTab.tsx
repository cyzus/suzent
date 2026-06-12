import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import { GitHubSyncSection } from './GitHubSyncSection';
import { SettingsHeader } from './SettingsHeader';

type Notification = { text: string; isError: boolean };

export function DataTab({ onSyncComplete }: { onSyncComplete?: () => void }): React.ReactElement {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [notification, setNotification] = useState<Notification | null>(null);

  function notify(text: string, isError: boolean): void {
    setNotification({ text, isError });
  }

  return (
    <div className="space-y-6">
      <SettingsHeader title={t('settings.data.title')} subtitle={t('settings.data.subtitle')} />

      <GitHubSyncSection busy={busy} onBusyChange={setBusy} onNotify={notify} onSyncComplete={onSyncComplete} />

      {notification && (
        <div className={`border-4 border-brutal-black p-4 font-mono text-sm shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] ${notification.isError ? 'bg-red-100 text-brutal-black' : 'bg-green-100 text-brutal-black'}`}>
          {notification.text}
        </div>
      )}
    </div>
  );
}
