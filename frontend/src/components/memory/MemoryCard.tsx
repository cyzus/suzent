/**
 * Memory Card Component
 * Displays a single archival memory, content first — the text is the thing worth
 * reading, so metadata is demoted to a quiet footer and only shown when it says
 * something. Importance is a spine and a badge rather than a number: most rows sit
 * at the neutral 0.5, so a figure repeated on every card would be noise.
 *
 * The kind (or, for notebook pages and early records, the category) is the one
 * piece of metadata that gets prominence, because it is what makes a scrolled list
 * legible: a fact about you and a lesson learned should not look identical.
 */

import React, { useState } from 'react';
import type { ArchivalMemory } from '../../types/memory';
import { BrutalDeleteButton } from '../BrutalDeleteButton';
import { BrutalDeleteOverlay } from '../BrutalDeleteOverlay';
import { useI18n } from '../../i18n';
import { MemoryMarkdown, stripFrontmatter } from './MemoryMarkdown';
import { useChatStore } from '../../hooks/useChatStore';
import { memoryApi } from '../../lib/memoryApi';

interface MemoryCardProps {
  memory: ArchivalMemory;
  onDelete: (memoryId: string) => Promise<void>;
  searchQuery?: string;
  compact?: boolean;
  /** Clicking a topic on a card filters the list by it. */
  onTopicClick?: (topic: string) => void;
  activeTopics?: string[];
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

/** A typed memory is labelled by what it is about rather than by its category. */
const KIND_ACCENTS: Record<string, string> = {
  user: 'bg-brutal-yellow text-brutal-black',
  experience: 'bg-brutal-blue text-white',
  world: 'bg-white text-brutal-black dark:bg-zinc-700 dark:text-white',
};

/**
 * Opens the conversation a daily-log memory was captured in. The lookup runs on
 * click, not per card, since most cards are never traced back.
 */
const OriginLink: React.FC<{ memoryId: string }> = ({ memoryId }) => {
  const { t } = useI18n();
  const { loadChat, switchToView } = useChatStore();
  const [state, setState] = useState<'idle' | 'loading' | 'missing'>('idle');

  const open = async (): Promise<void> => {
    setState('loading');
    try {
      const origin = await memoryApi.getMemoryOrigin(memoryId);
      if (!origin?.chat_id) {
        setState('missing');
        return;
      }
      setState('idle');
      loadChat(origin.chat_id);
      switchToView?.('chat');
    } catch {
      setState('missing');
    }
  };

  if (state === 'missing') {
    return <span className="italic">{t('memoryCard.origin.missing')}</span>;
  }
  return (
    <button
      onClick={() => void open()}
      disabled={state === 'loading'}
      className="font-bold text-neutral-600 hover:text-brutal-black hover:underline disabled:opacity-50 dark:text-neutral-300 dark:hover:text-white"
    >
      {t('memoryCard.origin.link')}
    </button>
  );
};

/** Escape a user-typed query so it can go into a RegExp literal safely. */
function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Plain-text reduction, for the compact row only.
 *
 * The full card renders markdown properly (see `MemoryMarkdown`), but a compact row
 * is one truncated line: a heading or a code fence has nowhere to go there, so the
 * markers are dropped rather than rendered.
 */
function readableContent(raw: string): string {
  return stripFrontmatter(raw)
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
  onTopicClick,
  activeTopics = [],
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

  const topics: string[] = memory.metadata?.topics || [];
  const kind = memory.metadata?.kind as string | undefined;
  const category = memory.metadata?.category as string | undefined;
  const typedKind = kind && kind in KIND_ACCENTS ? kind : undefined;
  const badgeLabel = typedKind ? t(`memoryCard.kind.${typedKind}`) : category?.replace(/_/g, ' ');
  const categoryAccent = typedKind
    ? KIND_ACCENTS[typedKind]
    : (category && CATEGORY_ACCENTS[category]) || DEFAULT_ACCENT;
  const isLogged = memory.metadata?.source_type === 'archive_log';
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
              {badgeLabel && (
                <span
                  className={`border border-brutal-black px-1 font-bold uppercase ${categoryAccent}`}
                >
                  {badgeLabel}
                </span>
              )}
              <span className="font-bold uppercase">{formatDate(memory.created_at)}</span>
              {!isLogged && sourceFile && <span className="truncate font-mono">{sourceFile}</span>}
              {topics.length > 0 && <span className="font-mono">{topics[0]}</span>}
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
          {/* Content leads. Collapsed cards clamp by height rather than by line
              count: markdown emits headings, lists and code blocks of differing
              heights, so `line-clamp` would cut a long card and a short one to
              visibly different sizes. The clamp is deep enough to show a table's
              header plus a few rows — cutting one after its header alone reads
              as a rendering bug rather than as an excerpt. */}
          <div
            className={`relative max-w-[68ch] text-brutal-black dark:text-neutral-100 ${
              !isExpanded && shouldTruncate ? 'max-h-56 overflow-hidden' : ''
            }`}
          >
            <MemoryMarkdown content={memory.content} searchQuery={searchQuery} />
            {!isExpanded && shouldTruncate && (
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white to-transparent dark:from-zinc-800" />
            )}
          </div>
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
            {badgeLabel && (
              <span
                className={`border border-brutal-black px-1 font-bold uppercase tracking-wide ${categoryAccent}`}
              >
                {badgeLabel}
              </span>
            )}

            <span className="font-bold uppercase tracking-wide">
              {formatDate(memory.created_at)}
            </span>

            {/* A daily-log file name says nothing; the conversation behind it does. */}
            {isLogged ? (
              <OriginLink memoryId={memory.id} />
            ) : (
              sourceFile && (
                <span className="font-mono" title={String(category || '')}>
                  {sourceFile}
                </span>
              )
            )}

            {topics.slice(0, 3).map((topic: string) =>
              onTopicClick ? (
                <button
                  key={topic}
                  onClick={() => onTopicClick(topic)}
                  className={`font-mono transition-colors hover:text-brutal-black dark:hover:text-white ${
                    activeTopics.includes(topic)
                      ? 'font-bold text-brutal-black dark:text-white'
                      : 'text-neutral-400 dark:text-neutral-500'
                  }`}
                  title={t('memoryCard.meta.filterByTopic', { topic })}
                >
                  {topic}
                </button>
              ) : (
                <span key={topic} className="font-mono text-neutral-400 dark:text-neutral-500">
                  {topic}
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
