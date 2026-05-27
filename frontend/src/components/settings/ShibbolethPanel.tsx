import React, { useCallback, useState } from 'react';

import { useI18n } from '../../i18n';
import type { SyncProfile, SyncStatus } from '../../lib/dataApi';
import {
  disableEncryptedSecretSync,
  enableEncryptedSecretSync,
  lockShibboleth,
  registerDeviceMnemonic,
  rotateMnemonic,
  unlockMnemonic,
} from '../../lib/dataApi';

type NotificationHandler = (text: string, isError: boolean) => void;

interface ShibbolethPanelProps {
  profile: SyncProfile | undefined;
  syncStatus: SyncStatus | null;
  busy: boolean;
  onBusyChange: (busy: boolean) => void;
  onNotify: NotificationHandler;
  onChanged: () => Promise<void>;
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function MnemonicGrid({ words }: { words: string[] }): React.ReactElement {
  const [copied, setCopied] = useState(false);

  function copyAll(): void {
    void navigator.clipboard.writeText(words.join(' ')).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-1.5">
        {words.map((word, i) => (
          <div key={i} className="flex items-center gap-1.5 border-2 border-brutal-black bg-white dark:bg-zinc-900 px-2 py-1.5">
            <span className="text-[10px] font-bold text-neutral-400 w-4 shrink-0">{i + 1}</span>
            <span className="font-mono text-xs font-bold dark:text-white">{word}</span>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={copyAll}
        className="w-full px-3 py-1.5 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700 hover:bg-neutral-50"
      >
        {copied ? '✓ Copied' : 'Copy all words'}
      </button>
    </div>
  );
}

function MnemonicInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}): React.ReactElement {
  const words = value.trim() ? value.trim().split(/\s+/) : [];
  const count = words.length;
  const valid = count === 12 || count === 24;

  return (
    <div className="space-y-1">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? 'Enter your 12 recovery words separated by spaces'}
        rows={3}
        className="w-full bg-neutral-50 dark:bg-zinc-900 border-2 border-brutal-black px-3 py-2 font-mono text-xs focus:outline-none dark:text-white resize-none"
      />
      <p className={`text-[10px] font-bold ${valid ? 'text-brutal-green' : count > 0 ? 'text-red-500' : 'text-neutral-400'}`}>
        {count > 0 ? `${count} word${count !== 1 ? 's' : ''}${valid ? ' ✓' : ' (need 12)'}` : 'Paste or type your recovery words'}
      </p>
    </div>
  );
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

  type Mode = 'idle' | 'setup' | 'unlock' | 'rotate' | 'register';
  const [mode, setMode] = useState<Mode>('idle');
  const [generatedWords, setGeneratedWords] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [inputPhrase, setInputPhrase] = useState('');
  const [newPhrase, setNewPhrase] = useState('');
  const [newGenerated, setNewGenerated] = useState<string[]>([]);

  const enabled = profile?.encrypted_secret_sync_enabled ?? false;
  const unlocked = syncStatus?.shibboleth_unlocked ?? false;
  const rotation = syncStatus?.rotation_detected ?? null;

  const generateWords = useCallback(async () => {
    try {
      const res = await fetch('/api/sync/secrets/generate-mnemonic', { method: 'POST' });
      if (res.ok) {
        const data = await res.json() as { mnemonic: string };
        return data.mnemonic.split(' ');
      }
    } catch {
      // fall through to client-side generation
    }
    // client-side fallback using crypto
    const arr = new Uint16Array(12);
    crypto.getRandomValues(arr);
    return Array.from(arr).map(v => `word${v % 2048}`);
  }, []);

  async function startSetup(): Promise<void> {
    // Ask backend to generate a mnemonic
    try {
      const res = await fetch(`${(await import('../../lib/api')).getApiBase()}/sync/secrets/generate-mnemonic`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json() as { mnemonic: string };
        setGeneratedWords(data.mnemonic.split(' '));
      } else {
        throw new Error('Failed to generate mnemonic');
      }
    } catch {
      onNotify('Failed to generate recovery words', true);
      return;
    }
    setConfirmed(false);
    setMode('setup');
  }

  async function handleEnable(): Promise<void> {
    if (!profile || !confirmed) return;
    const mnemonic = generatedWords.join(' ');
    onBusyChange(true);
    try {
      await enableEncryptedSecretSync(profile.id, mnemonic);
      setMode('idle');
      setGeneratedWords([]);
      setConfirmed(false);
      await onChanged();
      onNotify(t('settings.data.shibbolethEnabled'), false);
    } catch (e) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(e) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleUnlock(): Promise<void> {
    if (!profile) return;
    onBusyChange(true);
    try {
      await unlockMnemonic(profile.id, inputPhrase.trim());
      setInputPhrase('');
      setMode('idle');
      await onChanged();
      onNotify(t('settings.data.shibbolethUnlocked'), false);
    } catch (e) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(e) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleRegister(): Promise<void> {
    if (!profile) return;
    onBusyChange(true);
    try {
      await registerDeviceMnemonic(profile.id, inputPhrase.trim());
      setInputPhrase('');
      setMode('idle');
      await onChanged();
      onNotify(t('settings.data.shibbolethUnlocked'), false);
    } catch (e) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(e) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function startRotate(): Promise<void> {
    try {
      const res = await fetch(`${(await import('../../lib/api')).getApiBase()}/sync/secrets/generate-mnemonic`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json() as { mnemonic: string };
        setNewGenerated(data.mnemonic.split(' '));
        setNewPhrase('');
        setConfirmed(false);
        setMode('rotate');
        return;
      }
    } catch { /* fall through */ }
    onNotify('Failed to generate new recovery words', true);
  }

  async function handleRotate(): Promise<void> {
    if (!profile || !confirmed) return;
    const mnemonic = newGenerated.length > 0 ? newGenerated.join(' ') : newPhrase.trim();
    onBusyChange(true);
    try {
      await rotateMnemonic(profile.id, mnemonic);
      setMode('idle');
      setNewGenerated([]);
      setNewPhrase('');
      setConfirmed(false);
      await onChanged();
      onNotify('Recovery words rotated. All other devices will be prompted to enter the new words.', false);
    } catch (e) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(e) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleDisable(): Promise<void> {
    if (!profile) return;
    onBusyChange(true);
    try {
      await disableEncryptedSecretSync(profile.id);
      setMode('idle');
      await onChanged();
      onNotify(t('settings.data.shibbolethDisabled'), false);
    } catch (e) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(e) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  async function handleLock(): Promise<void> {
    if (!profile) return;
    onBusyChange(true);
    try {
      await lockShibboleth(profile.id);
      setMode('idle');
      await onChanged();
      onNotify(t('settings.data.shibbolethLocked'), false);
    } catch (e) {
      onNotify(t('settings.data.githubFailed', { error: errMsg(e) }), true);
    } finally {
      onBusyChange(false);
    }
  }

  function cancel(): void {
    setMode('idle');
    setGeneratedWords([]);
    setInputPhrase('');
    setNewGenerated([]);
    setNewPhrase('');
    setConfirmed(false);
  }

  return (
    <div className="space-y-2">
      {/* Toggle row */}
      <div className="flex items-center justify-between gap-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2">
        <div className="flex-1 min-w-0">
          <span className="text-xs font-bold uppercase">{t('settings.data.shibbolethTitle')}</span>
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5 leading-tight">
            {t('settings.data.shibbolethHint')}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {enabled && (
            <span className={`text-[10px] font-bold uppercase ${unlocked ? 'text-brutal-green' : 'text-amber-600'}`}>
              {unlocked ? 'Active' : 'Locked'}
            </span>
          )}
          <button
            type="button"
            disabled={busy || !profile}
            onClick={enabled ? handleDisable : (syncStatus?.has_secret_bundles ? () => setMode('register') : startSetup)}
            title={enabled ? t('settings.data.shibbolethDisable') : t('settings.data.shibbolethSetup')}
            className={`relative w-10 h-5 border-2 border-brutal-black transition-colors disabled:opacity-40 ${enabled ? 'bg-brutal-green' : 'bg-neutral-200 dark:bg-zinc-700'}`}
          >
            <span className={`absolute top-0.5 w-3 h-3 bg-brutal-black transition-all ${enabled ? 'left-[18px]' : 'left-0.5'}`} />
          </button>
        </div>
      </div>

      {/* Rotation detected banner */}
      {rotation?.rotation_detected && mode === 'idle' && (
        <div className="border-2 border-brutal-yellow bg-brutal-yellow/20 p-3 space-y-2">
          <p className="text-xs font-bold uppercase">Recovery words changed</p>
          <p className="text-[11px] text-neutral-700 dark:text-neutral-300">
            Recovery words were rotated on <strong>{rotation.rotated_by_device}</strong>
            {rotation.rotated_at ? ` on ${new Date(rotation.rotated_at).toLocaleDateString()}` : ''}.
            Enter your new words to continue syncing API keys.
          </p>
          <button
            type="button"
            onClick={() => setMode('register')}
            className="px-3 py-1.5 bg-brutal-black border-2 border-brutal-black font-bold uppercase text-xs text-white"
          >
            Enter new words
          </button>
        </div>
      )}

      {/* Setup: show generated words */}
      {mode === 'setup' && (
        <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-3 space-y-3">
          <p className="text-xs font-bold uppercase">Your recovery words</p>
          <p className="text-[11px] text-neutral-600 dark:text-neutral-400 leading-tight">
            {t('settings.data.shibbolethWarning')}
          </p>
          <MnemonicGrid words={generatedWords} />
          <label className="flex items-start gap-2 text-[11px] text-neutral-700 dark:text-neutral-300 cursor-pointer">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 shrink-0" />
            I have saved these words in a safe place
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !confirmed}
              onClick={handleEnable}
              className="px-3 py-1.5 bg-brutal-green border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
            >
              {t('settings.data.shibbolethEnable')}
            </button>
            <button type="button" disabled={busy} onClick={cancel} className="px-3 py-1.5 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs">
              Cancel
            </button>
          </div>
          <p className="text-[10px] text-neutral-400 pt-1">
            Already have recovery words?{' '}
            <button type="button" onClick={() => setMode('register')} className="underline font-bold hover:text-neutral-600">
              Enter existing words instead
            </button>
          </p>
        </div>
      )}

      {/* Unlock: enter existing words */}
      {mode === 'unlock' && (
        <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-3 space-y-2">
          <p className="text-xs font-bold uppercase">Enter recovery words</p>
          <MnemonicInput value={inputPhrase} onChange={setInputPhrase} />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={handleUnlock}
              className="px-3 py-1.5 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
            >
              {t('settings.data.shibbolethUnlockAction')}
            </button>
            <button type="button" disabled={busy} onClick={cancel} className="px-3 py-1.5 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Register device — enter existing words, or generate new if truly first time */}
      {mode === 'register' && (
        <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-3 space-y-2">
          <p className="text-xs font-bold uppercase">Enter your recovery words</p>
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400 leading-tight">
            Enter the 12 recovery words from the device where you originally set this up.
          </p>
          <MnemonicInput value={inputPhrase} onChange={setInputPhrase} placeholder="Enter your 12 recovery words" />
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              disabled={busy}
              onClick={handleRegister}
              className="px-3 py-1.5 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
            >
              Confirm
            </button>
            <button type="button" disabled={busy} onClick={cancel} className="px-3 py-1.5 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs">
              Cancel
            </button>
          </div>
          <p className="text-[10px] text-neutral-400 pt-1">
            Setting up for the first time?{' '}
            <button type="button" onClick={startSetup} className="underline font-bold hover:text-neutral-600">
              Generate new words instead
            </button>
          </p>

        </div>
      )}

      {/* Rotate: generate new words */}
      {mode === 'rotate' && (
        <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 p-3 space-y-3">
          <p className="text-xs font-bold uppercase">New recovery words</p>
          <p className="text-[11px] text-amber-700 dark:text-amber-400 leading-tight">
            All other devices will need to enter these new words before they can sync API keys again.
          </p>
          {newGenerated.length > 0 && <MnemonicGrid words={newGenerated} />}
          <label className="flex items-start gap-2 text-[11px] text-neutral-700 dark:text-neutral-300 cursor-pointer">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-0.5 shrink-0" />
            I have saved the new words and understand other devices will need updating
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy || !confirmed}
              onClick={handleRotate}
              className="px-3 py-1.5 bg-brutal-yellow border-2 border-brutal-black font-bold uppercase text-xs shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50"
            >
              Rotate words
            </button>
            <button type="button" disabled={busy} onClick={cancel} className="px-3 py-1.5 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Unlocked actions */}
      {enabled && unlocked && mode === 'idle' && (
        <div className="flex flex-wrap gap-2 justify-end">
          <button
            type="button"
            disabled={busy}
            onClick={startRotate}
            className="px-3 py-1 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700 hover:bg-amber-50 disabled:opacity-50"
          >
            Rotate words
          </button>
        </div>
      )}

      {/* Locked: show recovery unlock — only appears if keyring auto-unlock failed */}
      {enabled && !unlocked && mode === 'idle' && !rotation?.rotation_detected && (
        <div className="flex items-center justify-between border-2 border-amber-400 bg-amber-50 dark:bg-amber-900/20 px-3 py-2">
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            Recovery words needed — keyring unavailable on this device.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => setMode('unlock')}
            className="px-3 py-1.5 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 shrink-0 ml-3"
          >
            Enter words
          </button>
        </div>
      )}
    </div>
  );
}
