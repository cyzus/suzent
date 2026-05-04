import React, { useEffect, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';

import { useI18n } from '../../i18n';
import {
  DataStatus,
  exportData,
  fetchDataStatus,
  importData,
  previewImportData,
  previewSyncPull,
  syncPull,
  syncPush,
} from '../../lib/dataApi';

export function DataTab(): React.ReactElement {
  const { t } = useI18n();
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [syncTarget, setSyncTarget] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    fetchDataStatus().then(setStatus).catch(() => {
      setStatus(null);
      setIsError(true);
      setMessage(t('settings.data.statusFailed'));
    });
  }, []);

  async function handleExport(): Promise<void> {
    setBusy(true);
    setIsError(false);
    setMessage(t('settings.data.exporting'));
    try {
      const result = await exportData();
      setMessage(t('settings.data.exported', { path: result.output_path }));
    } catch (error) {
      setIsError(true);
      setMessage(
        t('settings.data.exportFailed', {
          error: error instanceof Error ? error.message : String(error),
        })
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(): Promise<void> {
    setBusy(true);
    setIsError(false);
    setMessage('');
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: 'SUZENT Export', extensions: ['zip'] }],
      });
      if (!selected || Array.isArray(selected)) return;

      const archive = String(selected);
      const preview = await previewImportData(archive);
      const confirmed = window.confirm(
        t('settings.data.importConfirm', { count: preview.entries.length })
      );
      if (!confirmed) return;

      setMessage(t('settings.data.importing'));
      const result = await importData(archive);
      setStatus(await fetchDataStatus());
      setMessage(
        t('settings.data.imported', {
          path: result.data_dir,
          backup: result.backup_path,
        })
      );
    } catch (error) {
      setIsError(true);
      setMessage(
        t('settings.data.importFailed', {
          error: error instanceof Error ? error.message : String(error),
        })
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSyncPush(): Promise<void> {
    if (!syncTarget.trim()) return;
    setBusy(true);
    setIsError(false);
    setMessage(t('settings.data.syncing'));
    try {
      const result = await syncPush(syncTarget.trim());
      setMessage(t('settings.data.synced', { path: result.output_path }));
    } catch (error) {
      setIsError(true);
      setMessage(
        t('settings.data.syncFailed', {
          error: error instanceof Error ? error.message : String(error),
        })
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSyncPull(): Promise<void> {
    if (!syncTarget.trim()) return;
    setBusy(true);
    setIsError(false);
    setMessage(t('settings.data.pulling'));
    try {
      const preview = await previewSyncPull(syncTarget.trim());
      const confirmed = window.confirm(
        t('settings.data.pullConfirm', { count: preview.entries.length })
      );
      if (!confirmed) return;

      const result = await syncPull(syncTarget.trim());
      setStatus(await fetchDataStatus());
      setMessage(
        t('settings.data.pulled', {
          path: result.data_dir,
          backup: result.backup_path,
        })
      );
    } catch (error) {
      setIsError(true);
      setMessage(
        t('settings.data.pullFailed', {
          error: error instanceof Error ? error.message : String(error),
        })
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-4xl font-brutal font-black uppercase text-brutal-black dark:text-white">{t('settings.data.title')}</h2>
      </div>

      <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6 mb-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-brutal-yellow border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-brutal-black">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">{t('settings.data.storageTitle')}</h3>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.data.subtitle')}</p>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-1">{t('settings.data.currentPath')}</div>
            <div className="font-mono text-xs border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2 break-all min-h-[2.25rem]">
              {status?.data_dir || t('settings.data.loading')}
            </div>
          </div>

          <div>
            <div className="text-xs font-bold uppercase text-neutral-500 dark:text-neutral-400 mb-2">{t('settings.data.portableEntries')}</div>
            <div className="flex flex-wrap gap-2">
              {(status?.portable_entries || []).map(entry => (
                <span key={entry} className="px-2 py-1 border-2 border-brutal-black text-xs font-mono bg-neutral-100 dark:bg-zinc-700">
                  {entry}
                </span>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-3 pt-1">
            <button
              type="button"
              disabled={busy}
              onClick={handleExport}
              className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs text-brutal-black shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 transition-colors active:shadow-none disabled:opacity-50"
            >
              {busy ? t('settings.data.working') : t('settings.data.export')}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleImport}
              className="px-4 py-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs text-brutal-black dark:text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] hover:brightness-110 transition-colors active:shadow-none disabled:opacity-50"
            >
              {t('settings.data.import')}
            </button>
            <span className="self-center text-xs text-neutral-600 dark:text-neutral-400">
              {t('settings.data.exportHint')}
            </span>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-zinc-800 dark:text-white border-4 border-brutal-black shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] p-6">
        <div className="flex items-start gap-4 mb-6">
          <div className="w-12 h-12 bg-brutal-blue border-2 border-brutal-black flex items-center justify-center shrink-0 shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] text-white">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 16V9m0 0l-3 3m3-3l3 3" />
            </svg>
          </div>
          <div>
            <h3 className="text-xl font-bold uppercase">{t('settings.data.syncTarget')}</h3>
            <p className="text-sm text-neutral-600 dark:text-neutral-400 mt-1">{t('settings.data.syncDesc')}</p>
          </div>
        </div>

        <div className="space-y-3">
          <input
            value={syncTarget}
            onChange={(event) => setSyncTarget(event.target.value)}
            placeholder={t('settings.data.syncPlaceholder')}
            className="w-full bg-white dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none focus:bg-neutral-50 dark:focus:bg-zinc-800 dark:text-white dark:placeholder-neutral-500"
          />
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy || !syncTarget.trim()}
              onClick={handleSyncPush}
              className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs text-brutal-black hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
            >
              {t('settings.data.syncPush')}
            </button>
            <button
              type="button"
              disabled={busy || !syncTarget.trim()}
              onClick={handleSyncPull}
              className="px-4 py-2 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs text-brutal-black dark:text-white hover:brightness-110 transition-colors shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] active:shadow-none disabled:opacity-50"
            >
              {t('settings.data.syncPull')}
            </button>
          </div>
        </div>
      </div>

      {message && (
        <div className={`border-4 border-brutal-black p-4 font-mono text-sm shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] ${isError ? 'bg-red-100 text-brutal-black' : 'bg-green-100 text-brutal-black'}`}>
          {message}
        </div>
      )}
    </div>
  );
}
