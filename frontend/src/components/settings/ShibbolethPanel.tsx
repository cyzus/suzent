import React, { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import type { SyncProfile, SyncStatus } from '../../lib/dataApi';
import {
  disableEncryptedSecretSync,
  enableEncryptedSecretSync,
  registerDeviceMnemonic,
  rotateMnemonic,
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

  type Mode = 'idle' | 'setup' | 'enter' | 'rotate';
  const [mode, setMode] = useState<Mode>('idle');
  const [generatedWords, setGeneratedWords] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [inputPhrase, setInputPhrase] = useState('');
  const [newGenerated, setNewGenerated] = useState<string[]>([]);

  const enabled = profile?.encrypted_secret_sync_enabled ?? false;
  const unlocked = syncStatus?.shibboleth_unlocked ?? false;
  const available = profile?.secret_sync_available ?? false;
  const rotation = syncStatus?.rotation_detected ?? null;

  const autoStarted = useRef(false);

  useEffect(() => {
    if (autoStarted.current || enabled || !profile) return;
    autoStarted.current = true;
    if (available) {
      setMode('enter');
    } else {
      void startSetup();
    }
  }, [profile?.id]);

  async function generateFromBackend(): Promise<string[]> {
    const res = await fetch(`${(await import('../../lib/api')).getApiBase()}/sync/secrets/generate-mnemonic`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to generate recovery words');
    const data = await res.json() as { mnemonic: string };
    return data.mnemonic.split(' ');
  }

  async function startSetup(): Promise<void> {
    try {
      setGeneratedWords(await generateFromBackend());
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

  async function handleEnterWords(): Promise<void> {
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
      setNewGenerated(await generateFromBackend());
      setConfirmed(false);
      setMode('rotate');
    } catch {
      onNotify('Failed to generate new recovery words', true);
    }
  }

  async function handleRotate(): Promise<void> {
    if (!profile || !confirmed) return;
    const mnemonic = newGenerated.join(' ');
    onBusyChange(true);
    try {
      await rotateMnemonic(profile.id, mnemonic);
      setMode('idle');
      setNewGenerated([]);
      setConfirmed(false);
      await onChanged();
      onNotify('Recovery words rotated. Other devices will be prompted to enter the new words.', false);
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

  function cancel(): void {
    setMode('idle');
    setGeneratedWords([]);
    setInputPhrase('');
    setNewGenerated([]);
    setConfirmed(false);
  }

  // Derive which state we're in
  const needsWords = enabled && !unlocked && !rotation?.rotation_detected;
  const needsNewWords = rotation?.rotation_detected;

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-900 px-3 py-2">
        <div className="flex-1 min-w-0">
          <span className="text-xs font-bold uppercase">Sync API keys</span>
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
        </div>
      </div>

      {/* Rotation banner */}
      {needsNewWords && mode === 'idle' && (
        <div className="border-2 border-brutal-yellow bg-brutal-yellow/20 p-3 space-y-2">
          <p className="text-xs font-bold uppercase">Recovery words changed</p>
          <p className="text-[11px] text-neutral-700 dark:text-neutral-300">
            Words were rotated on <strong>{rotation!.rotated_by_device}</strong>
            {rotation!.rotated_at ? ` on ${new Date(rotation!.rotated_at).toLocaleDateString()}` : ''}.
            Enter your new words to continue syncing API keys.
          </p>
          <button
            type="button"
            onClick={() => setMode('enter')}
            className="px-3 py-1.5 bg-brutal-black border-2 border-brutal-black font-bold uppercase text-xs text-white"
          >
            Enter new words
          </button>
        </div>
      )}

      {/* Keyring unavailable — locked fallback */}
      {needsWords && mode === 'idle' && (
        <div className="flex items-center justify-between border-2 border-amber-400 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 gap-3">
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            Recovery words needed — keyring unavailable on this device.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => setMode('enter')}
            className="px-3 py-1.5 bg-brutal-blue border-2 border-brutal-black font-bold uppercase text-xs text-white shadow-[2px_2px_0px_0px_rgba(0,0,0,1)] disabled:opacity-50 shrink-0"
          >
            Enter words
          </button>
        </div>
      )}

      {/* Setup: generate new words */}
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
          <div className="flex gap-2 flex-wrap">
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
            <button type="button" onClick={() => { cancel(); setMode('enter'); }} className="underline font-bold hover:text-neutral-600">
              Enter existing words instead
            </button>
          </p>
        </div>
      )}

      {/* Enter words: register device or fresh setup if no bundle exists */}
      {mode === 'enter' && (
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
              onClick={handleEnterWords}
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
            <button type="button" onClick={() => { cancel(); void startSetup(); }} className="underline font-bold hover:text-neutral-600">
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

      {/* Active actions */}
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
          <button
            type="button"
            disabled={busy}
            onClick={handleDisable}
            className="px-3 py-1 border-2 border-brutal-black font-bold uppercase text-xs bg-white dark:bg-zinc-700 hover:bg-red-50 disabled:opacity-50"
          >
            Disable
          </button>
        </div>
      )}
    </div>
  );
}
