import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { SettingsHeader } from './SettingsHeader';
import { SettingsPage } from './SettingsCard';

interface ModelRolesTabProps {
  roleModels: Record<string, string[]>;
  suggestions: Record<string, string[]>;
  unregisteredModels: string[];
  onOpenVoiceSettings?: () => void;
  onChange: (roles: Record<string, string[]>) => void;
}

type FallbackBehavior = 'none' | 'primary' | 'cheap' | 'decision' | 'vision-primary';

const ROLES: { key: string; labelKey: string; descKey: string; fallback: FallbackBehavior }[] = [
  { key: 'primary', labelKey: 'roles.primary', descKey: 'roles.primaryDesc', fallback: 'none' },
  { key: 'cheap', labelKey: 'roles.cheap', descKey: 'roles.cheapDesc', fallback: 'primary' },
  { key: 'decision', labelKey: 'roles.decision', descKey: 'roles.decisionDesc', fallback: 'cheap' },
  { key: 'title', labelKey: 'roles.autoTitle', descKey: 'roles.autoTitleDesc', fallback: 'cheap' },
  {
    key: 'memory_extraction',
    labelKey: 'roles.memoryExtraction',
    descKey: 'roles.memoryExtractionDesc',
    fallback: 'cheap',
  },
  { key: 'dream', labelKey: 'roles.dream', descKey: 'roles.dreamDesc', fallback: 'primary' },
  {
    key: 'goal_judge',
    labelKey: 'roles.goalJudge',
    descKey: 'roles.goalJudgeDesc',
    fallback: 'decision',
  },
  {
    key: 'permission_review',
    labelKey: 'roles.permissionReview',
    descKey: 'roles.permissionReviewDesc',
    fallback: 'decision',
  },
  {
    key: 'vision',
    labelKey: 'roles.vision',
    descKey: 'roles.visionDesc',
    fallback: 'vision-primary',
  },
  {
    key: 'embedding',
    labelKey: 'roles.embedding',
    descKey: 'roles.embeddingDesc',
    fallback: 'none',
  },
  {
    key: 'image_generation',
    labelKey: 'roles.imageGeneration',
    descKey: 'roles.imageGenerationDesc',
    fallback: 'none',
  },
  {
    key: 'image_edit',
    labelKey: 'roles.imageEdit',
    descKey: 'roles.imageEditDesc',
    fallback: 'none',
  },
  {
    key: 'video_generation',
    labelKey: 'roles.videoGeneration',
    descKey: 'roles.videoGenerationDesc',
    fallback: 'none',
  },
  { key: 'tts', labelKey: 'roles.tts', descKey: 'roles.ttsDesc', fallback: 'none' },
];

// ── Searchable dropdown ──────────────────────────────────────────────────────

interface ModelDropdownProps {
  label: string;
  options: string[];
  unregisteredModels: Set<string>;
  onSelect: (model: string) => void;
}

function ModelDropdown({ label, options, unregisteredModels, onSelect }: ModelDropdownProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = query.trim()
    ? options.filter((m) => m.toLowerCase().includes(query.toLowerCase()))
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
    if (open) {
      setOpen(false);
      setQuery('');
      return;
    }
    setOpen(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function handleSelect(model: string) {
    onSelect(model);
    setOpen(false);
    setQuery('');
    ref.current?.querySelector('button')?.focus();
  }

  const trimmed = query.trim();
  const isExistingOption = options.includes(trimmed);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={handleOpen}
        aria-expanded={open}
        className="w-full flex items-center justify-between gap-2 px-3 py-1.5 border-2 border-brutal-black bg-white dark:bg-zinc-800 dark:text-white font-mono font-bold text-xs hover:bg-brutal-yellow/20 brutal-btn"
      >
        <span className="min-w-0 truncate">{label}</span>
        <span className="text-[10px] opacity-60">▼</span>
      </button>

      {open && (
        <div className="mt-2 border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm">
          <div className="border-b-2 border-brutal-black">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && trimmed && options.includes(trimmed))
                  handleSelect(trimmed);
                if (e.key === 'Escape') {
                  setOpen(false);
                  setQuery('');
                  ref.current?.querySelector('button')?.focus();
                }
              }}
              aria-label={t('settings.roles.searchPlaceholder')}
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
            {filtered.map((m) => (
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
            {trimmed.includes('/') && !isExistingOption && filtered.length === 0 && (
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

interface RoleRowProps {
  role: (typeof ROLES)[number];
  selected: string[];
  inherited: string[];
  source: string | null;
  suggestions: string[];
  unregisteredModels: string[];
  onChange: (models: string[]) => void;
}

function RoleRow({
  role,
  selected,
  inherited,
  source,
  suggestions,
  unregisteredModels,
  onChange,
}: RoleRowProps): React.ReactElement {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);
  const [inherit, setInherit] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const label = t(`settings.${role.labelKey}`);
  const effective = selected.length ? selected : inherited;
  const isInherited = !selected.length && inherited.length > 0;

  function close(): void {
    setEditing(false);
    trigger.current?.focus();
  }

  function move(index: number, offset: number): void {
    const next = [...draft];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    setDraft(next);
  }

  return (
    <div className={editing ? 'bg-neutral-50 dark:bg-zinc-900' : ''}>
      <button
        ref={trigger}
        type="button"
        aria-expanded={editing}
        aria-controls={`role-editor-${role.key}`}
        onClick={() => {
          if (editing) close();
          else {
            setDraft([...selected]);
            setInherit(role.fallback !== 'none' && selected.length === 0);
            setEditing(true);
          }
        }}
        className="group grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left hover:bg-neutral-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-brutal-blue dark:hover:bg-zinc-900 sm:grid-cols-[minmax(8rem,0.8fr)_minmax(0,1.5fr)_auto]"
      >
        <span className="text-sm font-black uppercase tracking-wide">{label}</span>
        <span className="col-start-1 row-start-2 min-w-0 sm:col-start-2 sm:row-start-1">
          <span
            className={`block truncate font-mono text-xs ${effective.length ? '' : 'font-sans text-neutral-400'}`}
            title={effective.join(', ')}
          >
            {effective[0] || t('settings.roles.notConfigured')}
            {effective.length > 1 && (
              <span className="ml-2 font-sans text-neutral-500">+{effective.length - 1}</span>
            )}
          </span>
          <span className="mt-1 block text-[11px] text-neutral-500 dark:text-neutral-400">
            {isInherited
              ? t('settings.roles.fromRole', { role: source })
              : selected.length
                ? t('settings.roles.customStatus')
                : t('settings.roles.chooseModel')}
          </span>
        </span>
        <span className="col-start-2 row-start-1 row-span-2 flex items-center gap-2 text-xs text-neutral-500 sm:col-start-3 sm:row-span-1">
          <span
            className={`h-1.5 w-1.5 rounded-full ${selected.length ? 'bg-brutal-green' : isInherited ? 'bg-brutal-blue' : 'bg-neutral-300'}`}
            aria-hidden="true"
          />
          <span aria-hidden="true">{editing ? '−' : '+'}</span>
        </span>
      </button>
      {editing && (
        <div
          id={`role-editor-${role.key}`}
          className="space-y-3 border-t border-neutral-200 px-4 pb-4 pt-3 dark:border-zinc-700"
        >
          <p className="text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
            {t(`settings.${role.descKey}`)}
          </p>
          {role.fallback !== 'none' && (
            <fieldset className="flex flex-wrap gap-4 text-xs font-bold">
              <legend className="sr-only">{t('settings.roles.modelSource')}</legend>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  name={`source-${role.key}`}
                  checked={inherit}
                  onChange={() => setInherit(true)}
                />
                {t('settings.roles.inheritMode')}
              </label>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="radio"
                  name={`source-${role.key}`}
                  checked={!inherit}
                  onChange={() => setInherit(false)}
                />
                {t('settings.roles.customMode')}
              </label>
            </fieldset>
          )}
          {inherit ? (
            <p className="break-words text-xs text-neutral-600 dark:text-neutral-400">
              {inherited.length
                ? t('settings.roles.inheritPreview', { role: source, model: inherited[0] })
                : t('settings.roles.parentMissing')}
            </p>
          ) : (
            <div className="space-y-3">
              <p className="text-xs font-bold">{t('settings.roles.firstChoice')}</p>
              <ModelDropdown
                label={draft[0] || t('settings.roles.chooseModel')}
                options={[...new Set([...suggestions, ...unregisteredModels])]}
                unregisteredModels={new Set(unregisteredModels)}
                onSelect={(id) => {
                  const model = id.trim();
                  if (model) setDraft([model, ...draft.slice(1).filter((item) => item !== model)]);
                }}
              />
              {draft.length > 0 && role.fallback === 'none' && (
                <BrutalButton type="button" size="xs" onClick={() => setDraft([])}>
                  {t('settings.roles.clearRole')}
                </BrutalButton>
              )}
              {draft.length > 0 && (
                <details className="border-t border-neutral-200 pt-3 dark:border-zinc-700">
                  <summary className="cursor-pointer text-xs font-bold">
                    {t('settings.roles.backupModels', { count: draft.length - 1 })}
                  </summary>
                  <div className="mt-3 space-y-3">
                    <p className="text-[11px] text-neutral-500">{t('settings.roles.modelOrder')}</p>
                    <ol className="space-y-2">
                      {draft.slice(1).map((model, offset) => {
                        const index = offset + 1;
                        return (
                          <li
                            key={model}
                            className="flex flex-wrap items-center gap-2 border-2 border-brutal-black bg-white p-2 dark:bg-zinc-800"
                          >
                            <span className="min-w-0 flex-1 break-all font-mono text-xs">
                              {model}
                            </span>
                            <div className="flex gap-1">
                              <BrutalButton
                                size="sm"
                                type="button"
                                disabled={index === 1}
                                onClick={() => move(index, -1)}
                                aria-label={`${t('settings.roles.moveUp')}: ${model}`}
                              >
                                ↑
                              </BrutalButton>
                              <BrutalButton
                                size="sm"
                                type="button"
                                disabled={index === draft.length - 1}
                                onClick={() => move(index, 1)}
                                aria-label={`${t('settings.roles.moveDown')}: ${model}`}
                              >
                                ↓
                              </BrutalButton>
                              <BrutalButton
                                size="sm"
                                type="button"
                                onClick={() => setDraft(draft.filter((id) => id !== model))}
                                aria-label={`${t('common.remove')}: ${model}`}
                              >
                                ×
                              </BrutalButton>
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                    <ModelDropdown
                      label={t('settings.roles.addBackup')}
                      options={[...new Set([...suggestions, ...unregisteredModels])].filter(
                        (id) => !draft.includes(id)
                      )}
                      unregisteredModels={new Set(unregisteredModels)}
                      onSelect={(id) => {
                        const model = id.trim();
                        if (model && !draft.includes(model)) setDraft([...draft, model]);
                      }}
                    />
                  </div>
                </details>
              )}
            </div>
          )}
          <div className="flex items-center justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-zinc-700">
            <BrutalButton
              size="sm"
              type="button"
              className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue"
              onClick={close}
            >
              {t('common.cancel')}
            </BrutalButton>
            <BrutalButton
              size="sm"
              type="button"
              variant="primary"
              disabled={!inherit && role.fallback !== 'none' && draft.length === 0}
              onClick={() => {
                onChange(inherit ? [] : draft);
                close();
              }}
            >
              {t('settings.roles.applyChanges')}
            </BrutalButton>
          </div>
        </div>
      )}
    </div>
  );
}

export function ModelRolesTab({
  roleModels,
  suggestions,
  unregisteredModels,
  onChange,
  onOpenVoiceSettings,
}: ModelRolesTabProps): React.ReactElement {
  const { t } = useI18n();

  function resolveParent(fallback: FallbackBehavior): { models: string[]; source: string | null } {
    if (fallback === 'none') return { models: [], source: null };
    if (fallback === 'vision-primary')
      return {
        models: (roleModels.primary || []).filter((model) => suggestions.vision?.includes(model)),
        source: t('settings.roles.primary'),
      };
    const parent = ROLES.find((role) => role.key === fallback)!;
    const models = roleModels[fallback] || [];
    return models.length
      ? { models, source: t(`settings.${parent.labelKey}`) }
      : resolveParent(parent.fallback);
  }

  function renderRole(role: (typeof ROLES)[number]): React.ReactElement {
    const { models, source } = resolveParent(role.fallback);
    return (
      <RoleRow
        key={role.key}
        role={role}
        selected={roleModels[role.key] || []}
        inherited={models}
        source={source}
        suggestions={suggestions[role.key] || []}
        unregisteredModels={
          role.key === 'image_edit' ? suggestions._image_edit_unknown || [] : unregisteredModels
        }
        onChange={(selected) => onChange({ ...roleModels, [role.key]: selected })}
      />
    );
  }

  const groups = [
    { key: 'defaultsGroup', roles: ['primary', 'cheap', 'decision'] },
    { key: 'tasksGroup', roles: ['title', 'memory_extraction', 'dream'] },
    {
      key: 'specialistsGroup',
      roles: ['vision', 'embedding', 'image_generation', 'image_edit', 'video_generation', 'tts'],
    },
  ];

  return (
    <SettingsPage>
      <SettingsHeader
        title={t('settings.roles.title')}
        subtitle={t('settings.roles.compactIntro')}
      />
      {onOpenVoiceSettings && (
        <BrutalButton size="sm" onClick={onOpenVoiceSettings}>
          {t('speech.openSettings')}
        </BrutalButton>
      )}
      {groups.map((group) => (
        <section key={group.key} aria-labelledby={`roles-${group.key}`}>
          <h3
            id={`roles-${group.key}`}
            className="mb-2 text-sm font-black uppercase tracking-wide dark:text-white"
          >
            {t(`settings.roles.${group.key}`)}
          </h3>
          <div className="divide-y divide-neutral-200 border-2 border-brutal-black bg-white shadow-brutal-sm dark:divide-zinc-700 dark:bg-zinc-800 dark:text-white">
            {ROLES.filter((role) => group.roles.includes(role.key)).map(renderRole)}
            {group.key === 'defaultsGroup' && (
              <details>
                <summary className="cursor-pointer px-4 py-3 text-xs text-neutral-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue dark:text-neutral-400">
                  {t('settings.roles.advancedDecision')}
                  <span className="ml-2">
                    {t('settings.roles.overrideCount', {
                      count: ['goal_judge', 'permission_review'].filter(
                        (key) => roleModels[key]?.length
                      ).length,
                    })}
                  </span>
                </summary>
                <div className="divide-y divide-neutral-200 border-t border-neutral-200 dark:divide-zinc-700 dark:border-zinc-700">
                  {ROLES.filter((role) => role.fallback === 'decision').map(renderRole)}
                </div>
              </details>
            )}
          </div>
        </section>
      ))}
    </SettingsPage>
  );
}
