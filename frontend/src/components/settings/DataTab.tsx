import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import { GitHubSyncSection } from './GitHubSyncSection';

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
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black dark:text-white">{t('settings.data.title')}</h2>
      </div>

      <GitHubSyncSection busy={busy} onBusyChange={setBusy} onNotify={notify} onSyncComplete={onSyncComplete} />

      {notification && (
        <div className={`border-4 border-brutal-black p-4 font-mono text-sm shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] ${notification.isError ? 'bg-red-100 text-brutal-black' : 'bg-green-100 text-brutal-black'}`}>
          {notification.text}
        </div>
      )}
    </div>
  );
}
