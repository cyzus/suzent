import React, { useEffect, useMemo, useState } from 'react';
import { XMarkIcon, MagnifyingGlassIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { useSkills } from '../../hooks/useSkills';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { BrutalButton } from '../BrutalButton';
import { useI18n } from '../../i18n';
import { Skill } from '../../types/skills';

/** Strip the light markdown skill descriptions carry so rows stay single-line. */
function plainDescription(description?: string): string {
  return (description || '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\*\*([^*]*)\*\*/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

export const SkillsView: React.FC = () => {
  const { skills, loading, error, loadSkills, reload, toggle } = useSkills();
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [query, setQuery] = useState('');
  const [enabledOnly, setEnabledOnly] = useState(false);
  const { t } = useI18n();

  useEffect(() => {
    loadSkills();
  }, []);

  useEffect(() => {
    if (!selectedSkill) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSelectedSkill(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedSkill]);

  const enabledCount = useMemo(() => skills.filter((s) => s.enabled).length, [skills]);

  const visibleSkills = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return skills.filter((skill) => {
      if (enabledOnly && !skill.enabled) return false;
      if (!needle) return true;
      return (
        skill.name.toLowerCase().includes(needle) ||
        (skill.description || '').toLowerCase().includes(needle)
      );
    });
  }, [skills, query, enabledOnly]);

  if (loading && skills.length === 0) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center p-8">
        <div className="border-3 border-brutal-black bg-white dark:bg-zinc-800 p-6 shadow-[8px_8px_0px_0px_rgba(0,0,0,1)]">
          <h2 className="font-brutal text-2xl uppercase mb-4 animate-pulse">
            {t('skills.loading')}
          </h2>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="border-3 border-brutal-red bg-white dark:bg-zinc-800 p-6 shadow-brutal">
          <h3 className="font-brutal text-xl text-brutal-red mb-2 uppercase">
            {t('skills.errorTitle')}
          </h3>
          <p className="font-mono text-sm">{error}</p>
          <BrutalButton onClick={() => loadSkills()} size="sm" className="mt-4">
            {t('skills.retry')}
          </BrutalButton>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-y-auto px-4 md:px-6 py-5 space-y-4 max-w-5xl mx-auto scrollbar-thin">
      <div className="bg-white dark:bg-zinc-800 px-3 py-2 border-2 border-brutal-black shadow-brutal-sm flex flex-wrap items-center gap-2">
        <div className="min-w-0 mr-auto">
          <h2 className="font-brutal text-lg uppercase tracking-tighter leading-none">
            {t('skills.title')}
          </h2>
          <p className="text-[11px] font-mono text-neutral-500 dark:text-neutral-400">
            {t('skills.enabledCount', { enabled: enabledCount, total: skills.length })}
          </p>
        </div>
        <div className="relative">
          <MagnifyingGlassIcon className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-neutral-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('skills.searchPlaceholder')}
            aria-label={t('skills.searchPlaceholder')}
            className="w-40 sm:w-56 border-2 border-brutal-black bg-white dark:bg-zinc-900 py-1 pl-7 pr-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-brutal-yellow"
          />
        </div>
        <BrutalButton
          onClick={() => setEnabledOnly((value) => !value)}
          size="xs"
          isActive={enabledOnly}
          title={t('skills.enabledOnly')}
        >
          {t('skills.enabledOnly')}
        </BrutalButton>
        <BrutalButton onClick={() => reload()} size="icon" title={t('skills.reload')}>
          <ArrowPathIcon className="h-4 w-4 stroke-2" />
        </BrutalButton>
      </div>

      <div className="border-2 border-brutal-black divide-y-2 divide-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm">
        {visibleSkills.map((skill) => (
          <div
            key={skill.name}
            role="button"
            tabIndex={0}
            title={skill.path}
            onClick={() => setSelectedSkill(skill)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                setSelectedSkill(skill);
              }
            }}
            className={`flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors hover:bg-neutral-100 dark:hover:bg-zinc-700 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-brutal-yellow ${!skill.enabled ? 'opacity-60' : ''}`}
          >
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                toggle(skill.name);
              }}
              className={`shrink-0 w-9 h-5 flex items-center border-2 border-brutal-black p-0.5 transition-colors ${skill.enabled ? 'bg-brutal-green justify-end' : 'bg-white dark:bg-zinc-700 justify-start'}`}
              title={skill.enabled ? t('skills.disableSkill') : t('skills.enableSkill')}
              aria-pressed={skill.enabled}
            >
              <div
                className={`w-3 h-3 border-2 border-brutal-black ${skill.enabled ? 'bg-white' : 'bg-neutral-300 dark:bg-zinc-500'}`}
              />
            </button>
            <div className="min-w-0 flex-1 flex flex-col sm:flex-row sm:items-baseline sm:gap-3">
              <span className="font-mono text-xs font-black uppercase truncate sm:max-w-[16rem] sm:shrink-0">
                {skill.name}
              </span>
              <span className="min-w-0 truncate text-[11px] text-neutral-600 dark:text-neutral-400">
                {plainDescription(skill.description)}
              </span>
            </div>
            {skill.source && (
              <span className="shrink-0 hidden md:inline border-2 border-brutal-black px-1.5 py-0.5 font-mono text-[9px] uppercase text-neutral-600 dark:text-neutral-300">
                {skill.source}
              </span>
            )}
          </div>
        ))}
        {visibleSkills.length === 0 && (
          <div className="text-center p-10">
            <p className="font-mono text-neutral-400">
              {skills.length === 0 ? t('skills.emptyTitle') : t('skills.noMatches')}
            </p>
            {skills.length === 0 && (
              <p className="text-sm text-neutral-400 mt-2">{t('skills.emptyDesc')}</p>
            )}
          </div>
        )}
      </div>

      {selectedSkill && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="skill-detail-title"
          onClick={() => setSelectedSkill(null)}
        >
          <div
            className="w-full max-w-5xl max-h-[88vh] overflow-hidden bg-white dark:bg-zinc-900 border-3 border-brutal-black shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] flex flex-col"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b-3 border-brutal-black p-4 bg-white dark:bg-zinc-800">
              <div className="min-w-0">
                <h3 id="skill-detail-title" className="font-brutal text-2xl uppercase break-words">
                  {selectedSkill.name}
                </h3>
                <p className="mt-2 font-mono text-xs text-neutral-500 dark:text-neutral-400 break-all">
                  {selectedSkill.path}
                </p>
              </div>
              <BrutalButton
                onClick={() => setSelectedSkill(null)}
                size="icon"
                title={t('skills.closeSkill')}
                aria-label={t('skills.closeSkill')}
                className="shrink-0"
              >
                <XMarkIcon className="h-5 w-5 stroke-[3]" />
              </BrutalButton>
            </div>
            <div className="overflow-y-auto p-5 md:p-7 scrollbar-thin">
              <div className="mb-5 border-b-2 border-neutral-200 dark:border-zinc-700 pb-4">
                <p className="font-mono text-xs uppercase text-neutral-500 dark:text-neutral-400 mb-2">
                  {t('skills.description')}
                </p>
                <MarkdownRenderer content={selectedSkill.description || ''} />
              </div>
              <p className="font-mono text-xs uppercase text-neutral-500 dark:text-neutral-400 mb-2">
                {t('skills.mainBody')}
              </p>
              <MarkdownRenderer content={selectedSkill.body || ''} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
