/**
 * Core Memory Block Editor Component
 * Displays and allows editing of individual core memory blocks
 */

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../i18n';
import { BrutalButton } from '../BrutalButton';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import type { CoreMemoryLabel } from '../../types/memory';

interface CoreMemoryBlockProps {
  label: CoreMemoryLabel;
  content: string;
  onUpdate: (label: CoreMemoryLabel, content: string) => Promise<void>;
}

// Known core memory labels that have i18n keys
const KNOWN_LABELS = ['persona', 'user', 'facts', 'context'] as const;

// Helper to get label info with fallback for unknown labels
const getLabelInfo = (
  label: string,
  t: (key: string, params?: Record<string, unknown>) => string
): { title: string; description: string } => {
  if ((KNOWN_LABELS as readonly string[]).includes(label)) {
    return {
      title: t(`coreMemory.labels.${label}.title`),
      description: t(`coreMemory.labels.${label}.desc`),
    };
  }
  // Fallback for unknown labels - capitalize first letter
  const fallbackTitle = label.charAt(0).toUpperCase() + label.slice(1);
  return {
    title: fallbackTitle,
    description: `Custom memory block: ${fallbackTitle}`,
  };
};

const countWords = (text: string): number => {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
};

export const CoreMemoryBlock: React.FC<CoreMemoryBlockProps> = ({ label, content, onUpdate }) => {
  const { t } = useI18n();
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setEditContent(content);
    setHasUnsavedChanges(false);
  }, [content]);

  useEffect(() => {
    setHasUnsavedChanges(editContent !== content);
  }, [editContent, content]);

  const handleSave = async () => {
    if (editContent === content) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await onUpdate(label, editContent);
      setIsEditing(false);
      setHasUnsavedChanges(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('coreMemory.failedToSave'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setEditContent(content);
    setIsEditing(false);
    setError(null);
    setHasUnsavedChanges(false);
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  /** Grow the box with the text so editing never happens through a peephole. */
  const autoResize = (element: HTMLTextAreaElement) => {
    element.style.height = 'auto';
    element.style.height = `${element.scrollHeight}px`;
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      handleCancel();
    } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      if (hasUnsavedChanges && !isSaving) handleSave();
    }
  };

  const { title, description } = getLabelInfo(label, t);
  const viewedContent = isEditing ? editContent : content;
  const characterCount = viewedContent.length;

  return (
    <section
      className={`border-3 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal transition-all ${
        hasUnsavedChanges && isEditing ? 'ring-4 ring-brutal-black' : ''
      }`}
    >
      {/* Header — same rhythm as the section headers around it */}
      <header className="flex items-start justify-between gap-3 border-b-2 border-brutal-black px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-brutal text-base uppercase leading-none tracking-tight text-brutal-black dark:text-white">
              {title}
            </h3>
            {hasUnsavedChanges && isEditing && (
              <span className="border-2 border-brutal-black bg-brutal-black px-1.5 text-[10px] font-bold uppercase text-white animate-brutal-blink">
                {t('common.unsaved')}
              </span>
            )}
          </div>
          <p className="truncate font-mono text-[11px] text-neutral-600 dark:text-neutral-400">
            {description}
          </p>
        </div>

        <div className="flex shrink-0 gap-2">
          {!isEditing ? (
            <>
              <BrutalButton onClick={handleCopy} size="xs" disabled={!content}>
                {copied ? t('coreMemory.copiedText') : t('common.copy')}
              </BrutalButton>
              <BrutalButton onClick={() => setIsEditing(true)} size="xs">
                {t('common.edit')}
              </BrutalButton>
            </>
          ) : (
            <>
              <BrutalButton onClick={handleCancel} size="xs" disabled={isSaving}>
                {t('common.cancel')}
              </BrutalButton>
              <BrutalButton
                onClick={handleSave}
                size="xs"
                variant="dark"
                disabled={isSaving || !hasUnsavedChanges}
              >
                {isSaving ? t('common.saving') : t('common.save')}
              </BrutalButton>
            </>
          )}
        </div>
      </header>

      <div className="p-3">
        {error && (
          <div className="mb-3 flex items-start gap-2 border-2 border-brutal-red bg-white px-3 py-2 text-sm text-brutal-black dark:bg-zinc-900 dark:text-white">
            <span className="text-lg leading-none">⚠️</span>
            <div>
              <p className="font-bold">{t('coreMemory.saveFailed')}</p>
              <p className="mt-0.5 text-xs">{error}</p>
            </div>
          </div>
        )}

        {isEditing ? (
          <>
            <textarea
              value={editContent}
              onChange={(e) => {
                setEditContent(e.target.value);
                autoResize(e.target);
              }}
              onKeyDown={handleKeyDown}
              className="scrollbar-thin w-full min-h-[150px] resize-y border-2 border-brutal-black bg-white p-3 font-mono text-sm leading-6 text-brutal-black transition-all focus:outline-none focus:ring-4 focus:ring-brutal-black dark:bg-zinc-900 dark:text-white"
              placeholder={t('coreMemory.placeholder', { title: title.toLowerCase() })}
              autoFocus
              onFocus={(e) => autoResize(e.target)}
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-neutral-500 dark:text-neutral-400">
              <span>
                {t('coreMemory.charactersCount', { count: characterCount })} ·{' '}
                {t('coreMemory.wordsApprox', { count: countWords(editContent) })}
              </span>
              <span className="font-mono">{t('coreMemory.editHint')}</span>
            </div>
          </>
        ) : content ? (
          <>
            {/* Core memory is markdown on disk, so read it as markdown. Tightened
                block spacing — default prose margins turn a short list into a page. */}
            <div className="scrollbar-thin max-h-[400px] overflow-y-auto overflow-x-hidden break-words bg-neutral-50 px-3 py-2 text-sm leading-6 dark:bg-zinc-900 [&_h1]:mt-3 [&_h1]:mb-1 [&_h2]:mt-3 [&_h2]:mb-1 [&_h3]:mt-3 [&_h3]:mb-1 [&_li]:my-0 [&_ol]:my-1 [&_p]:my-1 [&_ul]:my-1">
              <MarkdownRenderer content={content} streamingLite />
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-neutral-500 dark:text-neutral-400">
              <span>{t('coreMemory.charactersCount', { count: characterCount })}</span>
              <span>·</span>
              <span>{t('coreMemory.wordsApprox', { count: countWords(content) })}</span>
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center gap-3 border-2 border-dashed border-neutral-400 px-4 py-6 text-center dark:border-zinc-600">
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              {t('coreMemory.noContent')}
            </p>
            <BrutalButton onClick={() => setIsEditing(true)} size="xs">
              {t('coreMemory.addContent')}
            </BrutalButton>
          </div>
        )}
      </div>
    </section>
  );
};
