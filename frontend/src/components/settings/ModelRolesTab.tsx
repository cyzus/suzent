import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { SettingsHeader } from './SettingsHeader';
import { GridCard, SettingsGrid, SettingsPage } from './SettingsCard';

interface ModelRolesTabProps {
  roleModels: Record<string, string[]>;
  suggestions: Record<string, string[]>;
  unregisteredModels: string[];
  onChange: (roles: Record<string, string[]>) => void;
}

type FallbackBehavior = 'none' | 'primary' | 'vision-primary';

const ROLES: { key: string; labelKey: string; descKey: string; fallback: FallbackBehavior }[] = [
  { key: 'primary',          labelKey: 'roles.primary',          descKey: 'roles.primaryDesc',         fallback: 'none' },
  { key: 'cheap',            labelKey: 'roles.cheap',            descKey: 'roles.cheapDesc',           fallback: 'primary' },
  { key: 'vision',           labelKey: 'roles.vision',           descKey: 'roles.visionDesc',          fallback: 'vision-primary' },
  { key: 'embedding',        labelKey: 'roles.embedding',        descKey: 'roles.embeddingDesc',       fallback: 'none' },
  { key: 'image_generation', labelKey: 'roles.imageGeneration',  descKey: 'roles.imageGenerationDesc', fallback: 'none' },
  { key: 'tts',              labelKey: 'roles.tts',              descKey: 'roles.ttsDesc',             fallback: 'none' },
];

// ── Searchable dropdown ──────────────────────────────────────────────────────

interface ModelDropdownProps {
  options: string[];
  unregisteredModels: Set<string>;
  onSelect: (model: string) => void;
}

function ModelDropdown({ options, unregisteredModels, onSelect }: ModelDropdownProps) {
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
        <div className="absolute z-50 top-full mt-1 left-0 right-0 border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal">
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
                  className="flex w-full items-center justify-between gap-2 border-b border-neutral-100 px-3 py-2 text-left font-mono text-xs hover:bg-brutal-yellow dark:border-zinc-700 dark:text-white dark:hover:bg-brutal-yellow/20"
                  title={m}
                >
                  <span className="truncate">{m}</span>
                  {unregisteredModels.has(m) && (
                    <span className="shrink-0 border border-amber-700 bg-amber-100 px-1 py-0.5 font-sans text-[8px] font-black uppercase text-amber-900 dark:bg-amber-900/30 dark:text-amber-300">
                      {t('settings.roles.unverified')}
                    </span>
                  )}
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
  roleKey: string;
  label: string;
  desc: string;
  selected: string[];
  suggestions: string[];
  unregisteredModels: string[];
  fallback: FallbackBehavior;
  onChange: (models: string[]) => void;
}

function RoleCard({ roleKey, label, desc, selected, suggestions, unregisteredModels, fallback, onChange }: RoleCardProps) {
  const { t } = useI18n();

  const unregistered = new Set(unregisteredModels);
  const explicitOverrides = new Set(selected.filter((model) => !suggestions.includes(model)));
  const available = [...new Set([...suggestions, ...unregisteredModels])]
    .filter(m => !selected.includes(m));

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

  function moveDown(idx: number) {
    if (idx >= selected.length - 1) return;
    const next = [...selected];
    [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
    onChange(next);
  }

  function priorityLabel(index: number): string {
    if (index === 0) return t('settings.roles.firstChoice');
    if (index === selected.length - 1) return t('settings.roles.lastResort');
    return t('settings.roles.fallbackNumber', { number: String(index) });
  }

  const emptyFallback = fallback === 'primary'
    ? t('settings.roles.inheritsPrimary')
    : fallback === 'vision-primary'
      ? t('settings.roles.inheritsVisionPrimary')
      : t('settings.roles.noImplicitFallback');

  return (
    <GridCard title={label} subtitle={desc} active={selected.length > 0}>
      {/* Body */}
      <div className="flex flex-1 flex-col gap-3 p-3">

        {/* Selected model chain */}
        {selected.length > 0 ? (
          <div>
            {selected.map((modelId, idx) => (
              <React.Fragment key={modelId}>
                <div className="grid grid-cols-[5.25rem_minmax(0,1fr)_auto] items-center gap-1.5">
                  <span className="text-[9px] font-black uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
                    {priorityLabel(idx)}
                  </span>
                  <span
                    className="flex min-w-0 items-center gap-1.5 border-2 border-brutal-black bg-neutral-50 px-2 py-1.5 font-mono text-xs dark:bg-zinc-700 dark:text-white"
                    title={modelId}
                  >
                    <span className="truncate">{modelId}</span>
                    {(unregistered.has(modelId) || explicitOverrides.has(modelId)) && (
                      <span
                        className="shrink-0 text-amber-700 dark:text-amber-300"
                        title={t('settings.roles.explicitOverride')}
                        aria-label={t('settings.roles.explicitOverride')}
                      >
                        ?
                      </span>
                    )}
                  </span>
                  <div className="flex items-center gap-1">
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
                {idx < selected.length - 1 ? (
                  <button
                    type="button"
                    onClick={() => moveDown(idx)}
                    className="w-6 h-6 flex items-center justify-center border-2 border-brutal-black bg-white dark:bg-zinc-700 hover:bg-neutral-100 dark:hover:bg-zinc-600 dark:text-white text-xs flex-shrink-0 font-bold"
                    title={t('settings.roles.moveDown')}
                  >↓</button>
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
                </div>
                {idx < selected.length - 1 && (
                  <div className="ml-[5.55rem] h-3 border-l-2 border-dashed border-neutral-400" aria-hidden="true" />
                )}
              </React.Fragment>
            ))}
            <p className="mt-2 border-t border-neutral-200 pt-2 text-[10px] leading-relaxed text-neutral-500 dark:border-zinc-600 dark:text-neutral-400">
              {t('settings.roles.chainStops')}
            </p>
          </div>
        ) : (
          <div className="border-2 border-dashed border-neutral-300 bg-neutral-50 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-900">
            <p className="text-[10px] font-black uppercase text-neutral-500 dark:text-neutral-400">
              {t('settings.roles.notConfigured')}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-neutral-600 dark:text-neutral-400">{emptyFallback}</p>
          </div>
        )}

        {/* Add model: searchable dropdown; typing a custom id also works */}
        <ModelDropdown options={available} unregisteredModels={unregistered} onSelect={addModel} />
        {unregisteredModels.length > 0 && roleKey !== 'primary' && roleKey !== 'cheap' && (
          <p className="text-[10px] leading-relaxed text-amber-800 dark:text-amber-300">
            {t('settings.roles.unregisteredAvailable')}
          </p>
        )}
      </div>
    </GridCard>
  );
}

// ── Tab ──────────────────────────────────────────────────────────────────────

export function ModelRolesTab({ roleModels, suggestions, unregisteredModels, onChange }: ModelRolesTabProps): React.ReactElement {
  const { t } = useI18n();

  return (
    <SettingsPage>
      <SettingsHeader title={t('settings.roles.title')} subtitle={t('settings.roles.subtitle')} />

      <SettingsGrid density="compact">
        {ROLES.map(({ key, labelKey, descKey, fallback }) => (
          <RoleCard
            key={key}
            roleKey={key}
            label={t(`settings.${labelKey}`)}
            desc={t(`settings.${descKey}`)}
            selected={roleModels[key] || []}
            suggestions={suggestions[key] || []}
            unregisteredModels={unregisteredModels}
            fallback={fallback}
            onChange={models => onChange({ ...roleModels, [key]: models })}
          />
        ))}
      </SettingsGrid>
    </SettingsPage>
  );
}
