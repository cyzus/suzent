import React from 'react';
import type { Message } from '../../types/api';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';
import { CompactionCube, CompactionSweep } from './CompactionCube';

/**
 * Small, self-contained presentational rows used by the chat view: the drag-drop
 * overlay, the connecting indicator, and the two non-conversational message kinds
 * (system-triggered turns and notices). Extracted from ChatWindow so they can be
 * reused and unit-tested independently — none depend on ChatWindow state, only on
 * their props.
 */

export const DragOverlay: React.FC = () => {
  const { t } = useI18n();
  return (
    <div className="absolute inset-0 z-50 bg-brutal-blue/20 border-4 border-dashed border-brutal-black flex items-center justify-center pointer-events-none">
      <div className="bg-brutal-yellow border-4 border-brutal-black shadow-brutal-xl px-8 py-6 flex flex-col items-center gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-brutal-black" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
        </svg>
        <span className="text-lg font-bold text-brutal-black uppercase">{t('chatWindow.dragDropTitle')}</span>
        <span className="text-sm text-brutal-black">{t('chatWindow.dragDropDesc')}</span>
      </div>
    </div>
  );
};

export const LoadingIndicator: React.FC = () => {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center p-4">
      <div className="bg-brutal-yellow border-2 border-brutal-black px-4 py-2 text-xs font-bold uppercase animate-pulse shadow-brutal-sm">
        {t('chatWindow.connecting')}
      </div>
    </div>
  );
};

export const SystemTriggeredMessage: React.FC<{ message: Message }> = ({ message }) => {
  const raw = (message.content || '').trim();
  if (!raw) return null;

  // Pull out the leading title: prefer a **bold** first line, else first line.
  const lines = raw.split('\n');
  const firstLine = lines[0].trim();
  const boldMatch = firstLine.match(/^\*\*(.+?)\*\*$/);
  const title = (boldMatch ? boldMatch[1] : firstLine).trim();
  const body = lines.slice(1).join('\n').trim();

  return (
    <div className="w-full max-w-3xl my-1 pl-2 md:pl-4">
      <div className="border-l-[3px] border-brutal-black/20 dark:border-neutral-700 px-4 py-2 opacity-50 hover:opacity-100 transition-opacity duration-300">
        {/* Title */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-brutal-black/60 dark:text-neutral-400 text-[10px] leading-none" aria-hidden="true">⏱</span>
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-brutal-black/60 dark:text-neutral-400 truncate">
            {title}
          </span>
        </div>

        {/* Body */}
        {body && (
          <div className="text-[12px] leading-relaxed text-brutal-black/80 dark:text-neutral-300">
            <MarkdownRenderer content={body} />
          </div>
        )}
      </div>
    </div>
  );
};

export const NoticeMessage: React.FC<{ message: Message }> = ({ message }) => {
  const content = message.content?.trim();
  if (!content) {
    return null;
  }

  // In-progress compaction notices end with "running..." (see
  // formatCompactLifecycleNotice / compactStageLabel). Show a live indicator so
  // the row reads as active work, not a completed one-shot notice.
  const isRunning = /running\.\.\.$/i.test(content) || /\bcompacting\b/i.test(content);

  return (
    <div className="w-full max-w-3xl pl-2 md:pl-6">
      <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-[2px_2px_0_0_#000] dark:shadow-[2px_2px_0_0_rgba(255,255,255,0.18)]">
        <div className="flex items-stretch">
          <div
            className={`w-1.5 self-stretch bg-brutal-black dark:bg-neutral-500 ${isRunning ? 'animate-pulse' : ''}`}
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1 flex items-center gap-3 px-3 py-2">
            {isRunning && <CompactionCube size={34} className="self-center" />}
            <div className="min-w-0">
              <div className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">Notice</div>
              <div className="text-sm leading-snug text-brutal-black dark:text-neutral-100">
                <MarkdownRenderer content={content} />
              </div>
            </div>
          </div>
        </div>
        {/* Compaction sweep footer — the whole box reads as actively compacting. */}
        {isRunning && (
          <CompactionSweep className="text-brutal-black dark:text-neutral-400" />
        )}
      </div>
    </div>
  );
};
