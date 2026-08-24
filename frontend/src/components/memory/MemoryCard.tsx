/**
 * Memory Card Component
 * Displays a single archival memory, content first — the text is the thing worth
 * reading, so metadata is demoted to a quiet footer and only shown when it says
 * something. Importance is a spine and a badge rather than a number: most rows sit
 * at the neutral 0.5, so a figure repeated on every card would be noise.
 *
 * The category is the one piece of metadata that gets prominence, because it is
 * what makes a scrolled list legible: a journal entry and a wiki concept should not
 * look identical.
 */

import React, { useState } from 'react';
import type { ArchivalMemory } from '../../types/memory';
import { BrutalDeleteButton } from '../BrutalDeleteButton';
import { BrutalDeleteOverlay } from '../BrutalDeleteOverlay';
import { useI18n } from '../../i18n';

interface MemoryCardProps {
  memory: ArchivalMemory;
  onDelete: (memoryId: string) => Promise<void>;
  searchQuery?: string;
  compact?: boolean;
  /** Clicking a tag on a card filters the list by it. */
  onTagClick?: (tag: string) => void;
  activeTags?: string[];
}

/**
 * Per-category card treatment. Only the accent varies — shape and spacing stay
 * constant so the list still reads as one list, not six competing ones.
 */
const CATEGORY_ACCENTS: Record<string, string> = {
  personal: 'bg-brutal-yellow text-brutal-black',
  preference: 'bg-brutal-yellow text-brutal-black',
  project: 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black',
  knowledge: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
  concept: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
  synthesis: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
  entity: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
  literature: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
  documentation: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
  inbox: 'bg-neutral-200 text-brutal-black dark:bg-zinc-600 dark:text-white',
  archive: 'bg-neutral-200 text-brutal-black dark:bg-zinc-600 dark:text-white',
  asset: 'bg-neutral-200 text-brutal-black dark:bg-zinc-600 dark:text-white',
  profile: 'bg-brutal-black text-white dark:bg-white dark:text-brutal-black',
};

const DEFAULT_ACCENT = 'bg-neutral-100 text-brutal-black dark:bg-zinc-700 dark:text-white';

/** Escape a user-typed query so it can go into a RegExp literal safely. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Memories are stored as light markdown. Full rendering would fight the card, but
 * leaving the syntax in makes prose read like source code — so drop the markers.
 */
function readableContent(raw: string): string {
  return raw
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1$2')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s*[-*]\s+/gm, '• ')
    .trim();
}

export const MemoryCard: React.FC<MemoryCardProps> = ({
  memory,
  onDelete,
  searchQuery,
  compact = false,
  onTagClick,
  activeTags = [],
}) => {
  const { t } = useI18n();
  const [isDeleting, setIsDeleting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(memory.id);
    } catch (error) {
      console.error('Failed to delete memory:', error);
      setIsDeleting(false);
      setShowConfirm(false);
    }
  };

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

      if (diffDays === 0) return t('memoryCard.today');
      if (diffDays === 1) return t('memoryCard.yesterday');
      if (diffDays < 7) return t('memoryCard.daysAgo', { count: String(diffDays) });

      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateString;
    }
  };

  const getImportanceLabel = (importance: number) => {
    if (importance >= 0.8) return t('memoryCard.importance.highShort');
    if (importance >= 0.5) return t('memoryCard.importance.medShort');
    return t('memoryCard.importance.lowShort');
  };

  const isRecent = () => {
    try {
      const date = new Date(memory.created_at);
      const now = new Date();
      const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
      return diffDays < 7;
    } catch {
      return false;
    }
  };

  const isFrequentlyAccessed = memory.access_count >= 5;

  const highlightText = (text: string, query?: string) => {
    if (!query || query.trim() === '') return text;

    const parts = text.split(new RegExp(`(${escapeRegExp(query)})`, 'gi'));
    return (
      <>
        {parts.map((part, i) =>
          part.toLowerCase() === query.toLowerCase() ? (
            <mark key={i} className="bg-brutal-yellow text-brutal-black font-bold px-0.5">
              {part}
            </mark>
          ) : (
            part
          )
        )}
      </>
    );
  };

  const tags: string[] = memory.metadata?.tags || [];
  const category = memory.metadata?.category as string | undefined;
  const categoryAccent = (category && CATEGORY_ACCENTS[category]) || DEFAULT_ACCENT;
  const sourceFile = memory.metadata?.source_file as string | undefined;
  const content = readableContent(memory.content);
  // Importance is a constant for indexed memories; only surface it when it deviates.
  const showImportance = memory.importance >= 0.8 || memory.importance < 0.5;
  // Roughly four lines of prose — past that the card needs a "show more".
  const shouldTruncate = content.length > 320;

  const spineClass =
    memory.importance >= 0.8
      ? 'bg-brutal-black dark:bg-white'
      : memory.importance >= 0.5
        ? 'bg-neutral-300 dark:bg-zinc-600'
        : 'bg-neutral-200 dark:bg-zinc-700';

  if (compact) {
    return (
      <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm hover:bg-neutral-50 dark:hover:bg-zinc-700 transition-all group relative">
        {/* Inline delete confirmation overlay */}
        {showConfirm && (
          <BrutalDeleteOverlay
            onConfirm={handleDelete}
            onCancel={() => setShowConfirm(false)}
            isDeleting={isDeleting}
            title={t('memoryCard.delete.confirmTitleCompact')}
            confirmText={t('memoryCard.delete.confirmYes')}
            layout="vertical"
          />
        )}

        <div className="p-2 flex items-center gap-3">
          {/* Importance Indicator */}
          <div
            className={`w-1.5 h-8 flex-shrink-0 ${spineClass}`}
            title={t('memoryCard.importance.tooltip', { value: memory.importance.toFixed(2) })}
          ></div>

          {/* Content Preview */}
          <div className="flex-1 min-w-0">
            <p className="truncate text-sm leading-6 text-brutal-black dark:text-neutral-100">
              {highlightText(content, searchQuery)}
            </p>
            <div className="flex items-center gap-2 text-[10px] text-neutral-500 dark:text-neutral-400 mt-0.5">
              {category && (
                <span className={`border border-brutal-black px-1 font-bold uppercase ${categoryAccent}`}>
                  {category.replace(/_/g, ' ')}
                </span>
              )}
              <span className="font-bold uppercase">{formatDate(memory.created_at)}</span>
              {sourceFile && <span className="truncate font-mono">{sourceFile}</span>}
              {tags.length > 0 && <span>#{tags[0]}</span>}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <BrutalDeleteButton
              onClick={() => setShowConfirm(true)}
              className="w-6 h-6 border opacity-0 group-hover:opacity-100 transition-opacity"
              title={t('memoryCard.delete.button')}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <article className="border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000] brutal-btn transition-all relative group">
      {/* Delete confirmation overlay */}
      {showConfirm && (
        <BrutalDeleteOverlay
          onConfirm={handleDelete}
          onCancel={() => setShowConfirm(false)}
          isDeleting={isDeleting}
          title={t('memoryCard.delete.confirmTitle')}
          confirmText={t('memoryCard.delete.confirmDelete')}
          cancelText={t('memoryCard.delete.cancel')}
          layout="vertical"
        />
      )}

      <div className="flex">
        {/* Importance spine — a glance-level cue that costs no vertical space */}
        <div
          className={`w-1.5 shrink-0 ${spineClass}`}
          title={t('memoryCard.importance.tooltip', { value: memory.importance.toFixed(2) })}
        />

        <div className="min-w-0 flex-1 p-4">
          {/* Content leads */}
          <p
            className={`max-w-[68ch] whitespace-pre-line break-words text-[15px] leading-7 text-brutal-black dark:text-neutral-100 ${
              !isExpanded && shouldTruncate ? 'line-clamp-4' : ''
            }`}
          >
            {highlightText(content, searchQuery)}
          </p>
          {shouldTruncate && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-2 inline-block border-b-2 border-transparent text-[11px] font-bold uppercase text-neutral-600 hover:border-brutal-black hover:text-brutal-black dark:text-neutral-400 dark:hover:border-white dark:hover:text-white"
            >
              {isExpanded ? t('memoryCard.showLess') : t('memoryCard.showMore')}
            </button>
          )}

          {/* Quiet footer: only what actually varies between memories */}
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-neutral-500 dark:text-neutral-400">
            {category && (
              <span
                className={`border border-brutal-black px-1 font-bold uppercase tracking-wide ${categoryAccent}`}
              >
                {category.replace(/_/g, ' ')}
              </span>
            )}

            <span className="font-bold uppercase tracking-wide">{formatDate(memory.created_at)}</span>

            {sourceFile && (
              <span className="font-mono" title={String(category || '')}>
                {sourceFile}
              </span>
            )}

            {tags.slice(0, 3).map((tag: string) =>
              onTagClick ? (
                <button
                  key={tag}
                  onClick={() => onTagClick(tag)}
                  className={`transition-colors hover:text-brutal-black dark:hover:text-white ${
                    activeTags.includes(tag)
                      ? 'font-bold text-brutal-black dark:text-white'
                      : 'text-neutral-400 dark:text-neutral-500'
                  }`}
                  title={t('memoryCard.meta.filterByTag', { tag })}
                >
                  #{tag}
                </button>
              ) : (
                <span key={tag} className="text-neutral-400 dark:text-neutral-500">
                  #{tag}
                </span>
              )
            )}

            {memory.access_count > 0 && (
              <span>
                {t('memoryCard.meta.views')} {memory.access_count}
              </span>
            )}

            {showImportance && (
              <span className="font-bold uppercase text-brutal-black dark:text-white">
                {getImportanceLabel(memory.importance)}
              </span>
            )}

            {isRecent() && (
              <span className="border border-brutal-black bg-brutal-yellow px-1 font-bold uppercase text-brutal-black">
                {t('memoryCard.badges.new')}
              </span>
            )}

            {isFrequentlyAccessed && (
              <span className="bg-brutal-black px-1 font-bold uppercase text-white dark:bg-white dark:text-brutal-black">
                {t('memoryCard.badges.hot')}
              </span>
            )}

            {memory.similarity !== undefined && memory.similarity > 0 && (
              <span className="font-bold text-brutal-black dark:text-white">
                {t('memoryCard.meta.match')} {(memory.similarity * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>

        {/* Delete button - only visible on hover */}
        <BrutalDeleteButton
          onClick={() => setShowConfirm(true)}
          className="absolute right-2 top-2 h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
          title={t('memoryCard.delete.buttonTitle')}
        />
      </div>
    </article>
  );
};
