import React, { useState } from 'react';

import { useI18n } from '../../i18n';
import type { SyncProfile, SyncStatus } from '../../lib/dataApi';
import {
  disableEncryptedSecretSync,
  enableEncryptedSecretSync,
  lockShibboleth,
  unlockShibboleth,
} from '../../lib/dataApi';

const MIN_LENGTH = 12;

type NotificationHandler = (text: string, isError: boolean) => void;

interface ShibbolethPanelProps {
  profile: SyncProfile | undefined;
  syncStatus: SyncStatus | null;
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
  onNotify: NotificationHandler;
  onChanged: () => Promise<void>;
}

export function ShibbolethPanel({
  profile,
  syncStatus,
  busy,
  onBusyChange,
  onNotify,
  onChanged,
}: ShibbolethPanelProps): React.ReactElement {
  const { t } = useI18n();
  const [passphrase, setPassphrase] = useState('');
  const [confirm, setConfirm] = useState('');
  const [unlockOnly, setUnlockOnly] = useState('');
  const [showSetup, setShowSetup] = useState(false);
  const [showUnlock, setShowUnlock] = useState(false);

  const enabled = profile?.encrypted_secret_sync_enabled ?? false;
  const unlocked = syncStatus?.shibboleth_unlocked ?? false;
  const hasBundles = syncStatus?.has_secret_bundles ?? false;

  async function handleEnable(): Promise<void> {
    if (!profile) return;
    if (passphrase.length < MIN_LENGTH) {
      onNotify(t('settings.data.shibbolethTooShort', { min: MIN_LENGTH }), true);
      return;
    }
    if (passphrase !== confirm) {
      onNotify(t('settings.data.shibbolethMismatch'), true);
      return;
    }
    onBusyChange(true);
    try {
      await enableEncryptedSecretSync(profile.id, passphrase);
      setPassphrase('');
      setConfirm('');
      setShowSetup(false);
      await onChanged();
      onNotify(t('settings.data.shibbolethEnabled'), false);
    } catch (error) {
      onNotify(
        t('settings.data.githubFailed', {
          error: error instanceof Error ? error.message : String(error),
        }),
        true,
      );
    } finally {
      onBusyChange(false);
    }
  }

  async function handleDisable(): Promise<void> {
    if (!profile) return;
    onBusyChange(true);
    try {
      await disableEncryptedSecretSync(profile.id);
      setPassphrase('');
      setConfirm('');
      setUnlockOnly('');
      setShowSetup(false);
      setShowUnlock(false);
      await onChanged();
      onNotify(t('settings.data.shibbolethDisabled'), false);
    } catch (error) {
      onNotify(
        t('settings.data.githubFailed', {
          error: error instanceof Error ? error.message : String(error),
        }),
        true,
      );
    } finally {
      onBusyChange(false);
    }
  }

  async function handleUnlock(): Promise<void> {
    if (!profile) return;
    if (unlockOnly.length < MIN_LENGTH) {
      onNotify(t('settings.data.shibbolethTooShort', { min: MIN_LENGTH }), true);
      return;
    }
    onBusyChange(true);
    try {
      await unlockShibboleth(profile.id, unlockOnly);
      setUnlockOnly('');
      setShowUnlock(false);
      await onChanged();
      onNotify(t('settings.data.shibbolethUnlocked'), false);
    } catch (error) {
      onNotify(
        t('settings.data.githubFailed', {
          error: error instanceof Error ? error.message : String(error),
        }),
        true,
      );
    } finally {
      onBusyChange(false);
    }
  }

  async function handleLock(): Promise<void> {
    if (!profile) return;
    onBusyChange(true);
    try {
      await lockShibboleth(profile.id);
      setUnlockOnly('');
      setShowUnlock(false);
      await onChanged();
      onNotify(t('settings.data.shibbolethLocked'), false);
    } catch (error) {
      onNotify(
        t('settings.data.githubFailed', {
          error: error instanceof Error ? error.message : String(error),
        }),
        true,
      );
    } finally {
      onBusyChange(false);
    }
  }

  return (
    <div className="border-4 border-brutal-black bg-amber-50 text-brutal-black mt-4 overflow-hidden">
      <div className="px-4 py-3 border-b-2 border-brutal-black bg-brutal-yellow flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-black uppercase tracking-wide">
            {t('settings.data.shibbolethTitle')}
          </div>
          <p className="text-xs mt-0.5 max-w-xl">{t('settings.data.shibbolethDesc')}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase ${
              enabled ? 'bg-brutal-green' : 'bg-neutral-200'
            }`}
          >
            {enabled ? t('settings.data.shibbolethOn') : t('settings.data.shibbolethOff')}
          </span>
          {enabled && (
            <span
              className={`px-2 py-1 border-2 border-brutal-black text-[10px] font-bold uppercase ${
                unlocked ? 'bg-brutal-green' : 'bg-red-200'
              }`}
            >
              {unlocked
                ? t('settings.data.shibbolethUnlockedBadge')
                : t('settings.data.shibbolethLockedBadge')}
            </span>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {!enabled && (
          <>
            <p className="text-xs leading-relaxed">{t('settings.data.shibbolethHint')}</p>
            {!showSetup ? (
              <button
                type="button"
                disabled={busy || !profile}
                onClick={() => setShowSetup(true)}
                className="px-4 py-2 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
              >
                {t('settings.data.shibbolethSetup')}
              </button>
            ) : (
              <div className="space-y-3 border-2 border-brutal-black bg-white p-4">
                <label className="block text-xs font-bold uppercase">
                  {t('settings.data.shibbolethLabel')}
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={passphrase}
                    onChange={(e) => setPassphrase(e.target.value)}
                    placeholder={t('settings.data.shibbolethPlaceholder')}
                    className="mt-1 w-full bg-neutral-50 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none"
                  />
                </label>
                <label className="block text-xs font-bold uppercase">
                  {t('settings.data.shibbolethConfirm')}
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="mt-1 w-full bg-neutral-50 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none"
                  />
                </label>
                <p className="text-[11px] text-neutral-600">{t('settings.data.shibbolethWarning')}</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleEnable}
                    className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
                  >
                    {t('settings.data.shibbolethEnable')}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setShowSetup(false);
                      setPassphrase('');
                      setConfirm('');
                    }}
                    className="px-4 py-2 bg-white border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]"
                  >
                    {t('common.cancel')}
                  </button>
                </div>
              </div>
            )}
          </>
        )}

        {enabled && (
          <>
            <p className="text-xs leading-relaxed">
              {hasBundles
                ? t('settings.data.shibbolethHasBundles')
                : t('settings.data.shibbolethNoBundles')}
            </p>
            <div className="flex flex-wrap gap-2">
              {!unlocked && !showUnlock && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setShowUnlock(true)}
                  className="px-4 py-2 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
                >
                  {t('settings.data.shibbolethUnlockAction')}
                </button>
              )}
              {unlocked && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={handleLock}
                  className="px-4 py-2 bg-white border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
                >
                  {t('settings.data.shibbolethLockAction')}
                </button>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={handleDisable}
                className="px-4 py-2 bg-red-200 border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
              >
                {t('settings.data.shibbolethDisable')}
              </button>
            </div>

            {showUnlock && !unlocked && (
              <div className="space-y-3 border-2 border-brutal-black bg-white p-4">
                <label className="block text-xs font-bold uppercase">
                  {t('settings.data.shibbolethLabel')}
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={unlockOnly}
                    onChange={(e) => setUnlockOnly(e.target.value)}
                    className="mt-1 w-full bg-neutral-50 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleUnlock}
                    className="px-4 py-2 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
                  >
                    {t('settings.data.shibbolethUnlockAction')}
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setShowUnlock(false);
                      setUnlockOnly('');
                    }}
                    className="px-4 py-2 bg-white border-2 border-brutal-black font-bold uppercase text-xs"
                  >
                    {t('common.cancel')}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
