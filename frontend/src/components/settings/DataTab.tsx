import React, { useEffect, useState } from 'react';

import { useI18n } from '../../i18n';
import { DataStatus, exportData, fetchDataStatus, syncPush } from '../../lib/dataApi';

export function DataTab(): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [syncTarget, setSyncTarget] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchDataStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  async function handleExport(): Promise<void> {
    setBusy(true);
    setMessage('');
    try {
      const result = await exportData();
      setMessage(t('settings.data.exported').replace('{path}', result.output_path));
    } finally {
      setBusy(false);
    }
  }

  async function handleSyncPush(): Promise<void> {
    if (!syncTarget.trim()) return;
    setBusy(true);
    setMessage('');
    try {
      const result = await syncPush(syncTarget.trim());
      setMessage(t('settings.data.synced').replace('{path}', result.output_path));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-brutal text-2xl uppercase mb-2">{t('settings.data.title')}</h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">{t('settings.data.subtitle')}</p>
      </div>

      <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-4 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
        <div className="text-xs uppercase font-bold text-neutral-500 mb-1">{t('settings.data.currentPath')}</div>
        <div className="font-mono text-sm break-all">{status?.data_dir || t('settings.data.loading')}</div>
      </div>

      <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-4 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
        <div className="text-xs uppercase font-bold text-neutral-500 mb-2">{t('settings.data.portableEntries')}</div>
        <div className="flex flex-wrap gap-2">
          {(status?.portable_entries || []).map(entry => (
            <span key={entry} className="px-2 py-1 border border-brutal-black text-xs font-mono bg-neutral-100 dark:bg-zinc-700">
              {entry}
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={handleExport}
          className="px-4 py-2 border-2 border-brutal-black bg-brutal-yellow text-brutal-black font-bold uppercase shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
        >
          {t('settings.data.export')}
        </button>
      </div>

      <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-4 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] space-y-3">
        <label className="block text-xs uppercase font-bold text-neutral-500">{t('settings.data.syncTarget')}</label>
        <input
          value={syncTarget}
          onChange={(event) => setSyncTarget(event.target.value)}
          placeholder={t('settings.data.syncPlaceholder')}
          className="w-full px-3 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-900 font-mono text-sm"
        />
        <button
          type="button"
          disabled={busy || !syncTarget.trim()}
          onClick={handleSyncPush}
          className="px-4 py-2 border-2 border-brutal-black bg-white dark:bg-zinc-700 font-bold uppercase shadow-[3px_3px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
        >
          {t('settings.data.syncPush')}
        </button>
      </div>

      {message && (
        <div className="border-2 border-brutal-black bg-green-100 text-brutal-black p-3 font-mono text-sm">
          {message}
        </div>
      )}
    </div>
  );
}
