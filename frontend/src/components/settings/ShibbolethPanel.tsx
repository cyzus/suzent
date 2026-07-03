import React, { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../i18n';
import type { SyncProfile, SyncStatus } from '../../lib/dataApi';
import {
  checkMnemonic,
  disableEncryptedSecretSync,
  enableEncryptedSecretSync,
  registerDeviceMnemonic,
  removeVaultKeys,
  rotateMnemonic,
  setSyncedKeys,
} from '../../lib/dataApi';
import { BrutalButton } from '../BrutalButton';
import { Badge, SettingsListAction } from './SettingsCard';

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

// Keys that belong to one provider must sync together — a BASE_URL without its
// API_KEY (or vice versa) is useless. Derive a provider group from the shared
// prefix by stripping a known credential suffix.
const KEY_SUFFIXES = ['_API_KEY', '_BASE_URL', '_API_BASE', '_MASTER_KEY', '_SECRET', '_TOKEN', '_KEY'];

function providerGroupOf(key: string): string {
  for (const suffix of KEY_SUFFIXES) {
    if (key.endsWith(suffix)) return key.slice(0, -suffix.length);
  }
  return key;
}

/** Group key names by provider prefix, preserving sorted order. */
function groupKeys(keys: string[]): { group: string; keys: string[] }[] {
  const map = new Map<string, string[]>();
  for (const key of [...keys].sort()) {
    const g = providerGroupOf(key);
    (map.get(g) ?? map.set(g, []).get(g)!).push(key);
  }
  return Array.from(map, ([group, ks]) => ({ group, keys: ks }));
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
  const [phraseMatch, setPhraseMatch] = useState<boolean | null>(null);

  const enabled = profile?.encrypted_secret_sync_enabled ?? false;
  const unlocked = syncStatus?.shibboleth_unlocked ?? false;
  const available = profile?.secret_sync_available ?? false;
  const rotation = syncStatus?.rotation_detected ?? null;
  const vault = syncStatus?.vault ?? null;

  const autoStarted = useRef(false);

  useEffect(() => {
    if (!profile) return;
    // Auto-open enter form when rotation is detected
    if (rotation?.rotation_detected && mode === 'idle') {
      setMode('enter');
      return;
    }
    if (autoStarted.current || enabled) return;
    autoStarted.current = true;
    if (available) {
      setMode('enter');
    } else {
      void startSetup();
    }
  }, [profile?.id, rotation?.rotation_detected]);

  // Live fingerprint check while entering words: does the typed phrase match the
  // existing vault? Debounced; only runs on a complete (12/24-word) phrase.
  useEffect(() => {
    if (!profile || mode !== 'enter') {
      setPhraseMatch(null);
      return;
    }
    const words = inputPhrase.trim().split(/\s+/).filter(Boolean);
    if (words.length !== 12 && words.length !== 24) {
      setPhraseMatch(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      checkMnemonic(profile.id, inputPhrase.trim())
        .then((r) => { if (!cancelled) setPhraseMatch(r.valid ? r.matches : null); })
        .catch(() => { if (!cancelled) setPhraseMatch(null); });
    }, 400);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [inputPhrase, mode, profile?.id]);

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

  async function toggleKeysSync(keys: string[], on: boolean): Promise<void> {
    if (!profile) return;
    // Current selection: explicit synced_keys, or (legacy null) treat as "all
    // local keys". We always persist an explicit list once the user touches it.
    const current = new Set(vault?.synced_keys ?? vault?.local_keys ?? []);
    for (const key of keys) {
      if (on) current.add(key);
      else current.delete(key);
    }
    try {
      await setSyncedKeys(profile.id, Array.from(current).sort());
      await onChanged();
    } catch (e) {
      onNotify(errMsg(e), true);
    }
  }

  async function removeProviderFromVault(group: string, keys: string[]): Promise<void> {
    if (!profile) return;
    const inVault = keys.filter((k) => (vault?.vault_keys ?? []).includes(k));
    if (inVault.length === 0) return;
    if (!window.confirm(
      `Remove ${group} (${inVault.join(', ')}) from the shared vault? Other devices will lose it on their next pull. Your local copy stays. Push afterwards to apply.`,
    )) return;
    onBusyChange(true);
    try {
      const { removed } = await removeVaultKeys(profile.id, inVault);
      await onChanged();
      onNotify(`Removed ${removed.length} key${removed.length !== 1 ? 's' : ''} from the vault — Push to propagate.`, false);
    } catch (e) {
      onNotify(errMsg(e), true);
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
          <span className="text-xs font-bold uppercase">Shared key vault</span>
          <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5 leading-tight">
            {t('settings.data.shibbolethHint')}
          </p>
        </div>
        {/* One prominent lock chip: the single clear locked/unlocked sign */}
        {enabled && (
          <Badge
            tone={unlocked ? 'green' : 'amber'}
            icon={<span aria-hidden>{unlocked ? '🔓' : '🔒'}</span>}
            title={unlocked ? 'Vault unlocked — keys can be pushed and fetched' : 'Vault locked — enter recovery words to push or fetch keys'}
            className="shrink-0"
          >
            {unlocked ? 'Unlocked' : 'Locked'}
          </Badge>
        )}
      </div>

      {/* Key inventory: what's in the vault vs. on this device. The one-glance
          fact that would have made the GEMINI-missing-from-vault bug obvious. */}
      {enabled && vault?.exists && (
        <div className="border-2 border-brutal-black bg-white dark:bg-zinc-900">
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 px-3 py-1.5 text-[9px] font-bold uppercase text-neutral-400 border-b-2 border-brutal-black/20">
            <span>Provider</span>
            <span className="text-center w-12">Vault</span>
            <span className="text-center w-14">Device</span>
            <span className="text-center w-10">Sync</span>
          </div>
          <div className="max-h-44 overflow-y-auto divide-y divide-brutal-black/10">
            {groupKeys(Array.from(new Set([...vault.vault_keys, ...vault.local_keys]))).map(
              ({ group, keys }) => {
                const syncedList = vault.synced_keys ?? vault.local_keys;
                // Provider syncs as a unit: on only when every key is synced.
                const allSynced = keys.every((k) => syncedList.includes(k));
                const someSynced = keys.some((k) => syncedList.includes(k));
                const anyInVault = keys.some((k) => vault.vault_keys.includes(k));
                return (
                  <div key={group}>
                    {/* Provider header + single Sync toggle — every provider renders
                        the same way, whether it has one key or several. */}
                    <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 px-3 py-1.5 items-center">
                      <span className="font-mono text-[11px] truncate dark:text-white font-bold flex items-center gap-2" title={keys.join(', ')}>
                        <span className="truncate">{group}<span className="ml-1 text-[9px] font-normal text-neutral-400 uppercase">({keys.length} key{keys.length !== 1 ? 's' : ''})</span></span>
                        {unlocked && anyInVault && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void removeProviderFromVault(group, keys)}
                            title="Remove this provider’s keys from the shared vault"
                            className="shrink-0 text-[9px] font-bold uppercase text-red-500 hover:text-red-600 disabled:opacity-40"
                          >
                            Remove
                          </button>
                        )}
                      </span>
                      <span className="w-12" />
                      <span className="w-14" />
                      <span className="text-center w-10">
                        <input
                          type="checkbox"
                          checked={allSynced}
                          ref={(el) => { if (el) el.indeterminate = someSynced && !allSynced; }}
                          disabled={busy}
                          onChange={(e) => void toggleKeysSync(keys, e.target.checked)}
                          title={keys.length > 1 ? 'Sync this provider’s keys together' : (allSynced ? 'Synced with vault' : 'Not synced — stays local only')}
                        />
                      </span>
                    </div>
                    {keys.map((key) => {
                      const m = vault.key_meta?.[key];
                      const inVault = vault.vault_keys.includes(key);
                      const onDevice = vault.local_keys.includes(key);
                      const keySynced = syncedList.includes(key);
                      // Local-only key: make the Vault "—" legible — will it upload?
                      const localOnlyHint = !inVault && onDevice
                        ? (keySynced ? '↑ will add to vault on Push' : 'local only')
                        : null;
                      return (
                        <div key={key} className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 px-3 py-1 items-center bg-neutral-50/60 dark:bg-zinc-800/40">
                          <span className="min-w-0 pl-3">
                            <span className="font-mono text-[10px] truncate text-neutral-500 dark:text-neutral-400 block" title={key}>{key}</span>
                            {m?.written_by && (
                              <span className="text-[9px] text-neutral-400 dark:text-neutral-500 truncate block" title={m.written_at ?? ''}>
                                by {m.written_by}{m.written_at ? ` · ${new Date(m.written_at).toLocaleDateString()}` : ''}
                              </span>
                            )}
                            {localOnlyHint && (
                              <span className={`text-[9px] truncate block ${keySynced ? 'text-brutal-blue font-bold' : 'text-neutral-400 dark:text-neutral-500'}`}>
                                {localOnlyHint}
                              </span>
                            )}
                          </span>
                          <span className={`text-center w-12 text-xs font-bold ${inVault ? 'text-brutal-green' : keySynced && onDevice ? 'text-brutal-blue' : 'text-red-400'}`}>{inVault ? '✓' : keySynced && onDevice ? '↑' : '—'}</span>
                          <span className={`text-center w-14 text-xs font-bold ${onDevice ? 'text-brutal-green' : 'text-neutral-300 dark:text-neutral-600'}`}>{onDevice ? '✓' : '—'}</span>
                          <span className="w-10" />
                        </div>
                      );
                    })}
                  </div>
                );
              },
            )}
          </div>
          <div className="px-3 py-1.5 border-t-2 border-brutal-black/20 text-[10px] text-neutral-500 dark:text-neutral-400 leading-tight">
            {vault.rotated_by_device && (
              <span>Last written by <span className="font-bold">{vault.rotated_by_device}</span>{vault.rotated_at ? ` · ${new Date(vault.rotated_at).toLocaleString()}` : ''}. </span>
            )}
            {!vault.this_device_enrolled && (
              <span className="text-amber-600 dark:text-amber-400 font-bold">This device is not enrolled — push to add its keys.</span>
            )}
          </div>
        </div>
      )}

      {/* Keyring unavailable — locked fallback */}
      {needsWords && mode === 'idle' && (
        <div className="flex items-center justify-between border-2 border-amber-400 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 gap-3">
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            Recovery words needed — keyring unavailable on this device.
          </p>
          <BrutalButton
            type="button"
            variant="primary"
            disabled={busy}
            onClick={() => setMode('enter')}
            className="px-3 py-1.5 text-xs uppercase shrink-0"
          >
            Enter words
          </BrutalButton>
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
            <BrutalButton
              type="button"
              variant="success"
              disabled={busy || !confirmed}
              onClick={handleEnable}
              className="px-3 py-1.5 text-xs uppercase"
            >
              {t('settings.data.shibbolethEnable')}
            </BrutalButton>
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
            {rotation?.rotation_detected
              ? `Words were rotated on ${rotation.rotated_by_device}${rotation.rotated_at ? ` on ${new Date(rotation.rotated_at).toLocaleDateString()}` : ''}. Enter the new words to continue syncing.`
              : 'Enter the 12 recovery words from the device where you originally set this up.'}
          </p>
          <MnemonicInput value={inputPhrase} onChange={setInputPhrase} placeholder="Enter your 12 recovery words" />
          {phraseMatch === true && (
            <p className="text-[10px] font-bold text-brutal-green">✓ Matches the existing vault — this device will join it.</p>
          )}
          {phraseMatch === false && (
            <p className="text-[10px] font-bold text-red-500 leading-tight">
              ✗ Different from the vault&apos;s words. Continuing will RE-KEY the vault and lock out other devices until they enter these new words.
            </p>
          )}
          <div className="flex gap-2 flex-wrap">
            <BrutalButton
              type="button"
              variant="primary"
              disabled={busy}
              onClick={handleEnterWords}
              className="px-3 py-1.5 text-xs uppercase"
            >
              Confirm
            </BrutalButton>
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
            <BrutalButton
              type="button"
              variant="warning"
              disabled={busy || !confirmed}
              onClick={handleRotate}
              className="px-3 py-1.5 text-xs uppercase"
            >
              Rotate words
            </BrutalButton>
            <button type="button" disabled={busy} onClick={cancel} className="px-3 py-1.5 bg-white dark:bg-zinc-700 border-2 border-brutal-black font-bold uppercase text-xs">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Active actions */}
      {enabled && unlocked && mode === 'idle' && (
        <div className="flex flex-wrap gap-2 justify-end">
          <SettingsListAction tone="neutral" disabled={busy} onClick={startRotate}>
            Rotate words
          </SettingsListAction>
          <SettingsListAction tone="red" disabled={busy} onClick={handleDisable}>
            Disable
          </SettingsListAction>
        </div>
      )}
    </div>
  );
}
