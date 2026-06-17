import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { GridCard } from './SettingsCard';

interface ModelRolesTabProps {
  roleModels: Record<string, string[]>;
  suggestions: Record<string, string[]>;
  onChange: (roles: Record<string, string[]>) => void;
}

const ROLES: { key: string; labelKey: string; descKey: string }[] = [
  { key: 'primary',          labelKey: 'roles.primary',          descKey: 'roles.primaryDesc' },
  { key: 'cheap',            labelKey: 'roles.cheap',            descKey: 'roles.cheapDesc' },
  { key: 'vision',           labelKey: 'roles.vision',           descKey: 'roles.visionDesc' },
  { key: 'embedding',        labelKey: 'roles.embedding',        descKey: 'roles.embeddingDesc' },
  { key: 'image_generation', labelKey: 'roles.imageGeneration',  descKey: 'roles.imageGenerationDesc' },
  { key: 'tts',              labelKey: 'roles.tts',              descKey: 'roles.ttsDesc' },
];

// ── Searchable dropdown ──────────────────────────────────────────────────────

interface ModelDropdownProps {
  options: string[];
  onSelect: (model: string) => void;
}

function ModelDropdown({ options, onSelect }: ModelDropdownProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = query.trim()
    ? options.filter(m => m.toLowerCase().includes(query.toLowerCase()))
    : options;

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  function handleOpen() {
    setOpen(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function handleSelect(model: string) {
    onSelect(model);
    setOpen(false);
    setQuery('');
  }

  const trimmed = query.trim();
  const isExistingOption = options.includes(trimmed);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={handleOpen}
        className="w-full flex items-center justify-between gap-2 px-3 py-1.5 border-2 border-brutal-black bg-white dark:bg-zinc-700 dark:text-white font-bold uppercase text-xs hover:bg-brutal-yellow/20 dark:hover:bg-brutal-yellow/10 brutal-btn"
      >
        <span>{t('settings.roles.addFromAvailable')}</span>
        <span className="text-[10px] opacity-60">▼</span>
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 right-0 border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)]">
          {/* Search doubles as custom-model entry: Enter adds the typed id */}
          <div className="border-b-2 border-brutal-black">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && trimmed) handleSelect(trimmed); }}
              placeholder={t('settings.roles.searchPlaceholder')}
              className="w-full px-3 py-2 font-mono text-xs bg-neutral-50 dark:bg-zinc-700 dark:text-white focus:outline-none"
              spellCheck={false}
            />
          </div>

          {/* Option list */}
          <ul className="max-h-48 overflow-y-auto">
            {filtered.length === 0 && !trimmed && (
              <li className="px-3 py-2 text-xs text-neutral-400 dark:text-neutral-500 italic">
                {t('settings.roles.noModelsFound')}
              </li>
            )}
            {filtered.map(m => (
              <li key={m}>
                <button
                  type="button"
                  onClick={() => handleSelect(m)}
                  className="w-full text-left px-3 py-2 font-mono text-xs hover:bg-brutal-yellow dark:hover:bg-brutal-yellow/20 border-b border-neutral-100 dark:border-zinc-700 truncate dark:text-white"
                  title={m}
                >
                  {m}
                </button>
              </li>
            ))}
            {trimmed && !isExistingOption && (
              <li>
                <button
                  type="button"
                  onClick={() => handleSelect(trimmed)}
                  className="w-full text-left px-3 py-2 font-mono text-xs font-bold hover:bg-brutal-yellow dark:hover:bg-brutal-yellow/20 border-t-2 border-brutal-black truncate dark:text-white"
                  title={trimmed}
                >
                  + {t('settings.roles.addCustom', { id: trimmed })}
                </button>
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Role card ────────────────────────────────────────────────────────────────

interface RoleCardProps {
  label: string;
  desc: string;
  selected: string[];
  suggestions: string[];
  onChange: (models: string[]) => void;
}

function RoleCard({ label, desc, selected, suggestions, onChange }: RoleCardProps) {
  const { t } = useI18n();

  const available = suggestions.filter(m => !selected.includes(m));

  function addModel(modelId: string) {
    const id = modelId.trim();
    if (id && !selected.includes(id)) onChange([...selected, id]);
  }

  function removeModel(modelId: string) {
    onChange(selected.filter(m => m !== modelId));
  }

  function moveUp(idx: number) {
    if (idx === 0) return;
    const next = [...selected];
    [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
    onChange(next);
  }

  return (
    <GridCard title={label} subtitle={desc} active={selected.length > 0}>
      {/* Body */}
      <div className="p-4 flex flex-col gap-3 flex-1">

        {/* Selected model chain */}
        {selected.length > 0 ? (
          <div className="space-y-1.5">
            {selected.map((modelId, idx) => (
              <div key={modelId} className="flex items-center gap-1.5">
                <span className="text-[10px] font-black w-5 h-5 flex items-center justify-center border-2 border-brutal-black bg-brutal-black text-white flex-shrink-0">
                  {idx + 1}
                </span>
                <span
                  className="flex-1 font-mono text-xs truncate border-2 border-brutal-black bg-neutral-50 dark:bg-zinc-700 dark:text-white px-2 py-1 shadow-[1px_1px_0px_0px_rgba(0,0,0,1)]"
                  title={modelId}
                >
                  {modelId}
                </span>
                {idx > 0 ? (
                  <button
                    type="button"
                    onClick={() => moveUp(idx)}
                    className="w-6 h-6 flex items-center justify-center border-2 border-brutal-black bg-white dark:bg-zinc-700 hover:bg-neutral-100 dark:hover:bg-zinc-600 dark:text-white text-xs flex-shrink-0 font-bold"
                    title={t('settings.roles.moveUp')}
                  >↑</button>
                ) : (
                  selected.length > 1 && <span className="w-6 h-6 flex-shrink-0" aria-hidden="true" />
                )}
                <button
                  type="button"
                  onClick={() => removeModel(modelId)}
                  className="w-6 h-6 flex items-center justify-center border-2 border-brutal-black bg-white dark:bg-zinc-700 hover:bg-red-50 dark:hover:bg-red-900/30 dark:text-white text-xs flex-shrink-0 font-bold"
                  title={t('common.remove')}
                >×</button>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-neutral-400 dark:text-neutral-500 italic border-2 border-dashed border-neutral-200 dark:border-zinc-600 px-3 py-2">
            {t('settings.roles.notConfigured')}
          </div>
        )}

        {/* Add model: searchable dropdown; typing a custom id also works */}
        <ModelDropdown options={available} onSelect={addModel} />
      </div>
    </GridCard>
  );
}

// ── Tab ──────────────────────────────────────────────────────────────────────

export function ModelRolesTab({ roleModels, suggestions, onChange }: ModelRolesTabProps): React.ReactElement {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <SettingsHeader title={t('settings.roles.title')} subtitle={t('settings.roles.subtitle')} />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
        {ROLES.map(({ key, labelKey, descKey }) => (
          <RoleCard
            key={key}
            label={t(`settings.${labelKey}`)}
            desc={t(`settings.${descKey}`)}
            selected={roleModels[key] || []}
            suggestions={suggestions[key] || []}
            onChange={models => onChange({ ...roleModels, [key]: models })}
          />
        ))}
      </div>
    </div>
  );
}
