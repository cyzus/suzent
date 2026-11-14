import React from 'react';
import type { Message } from '../../types/api';
import { useI18n } from '../../i18n';
import { MarkdownRenderer } from './MarkdownRenderer';
import { CompactionDivider } from './CompactionDivider';
import { compactionNoticeDetails } from '../../lib/compactionNotices';
import { DisclosureChevron } from '../DisclosureChevron';
import {
  ArrowTurnDownRightIcon,
  BoltIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon,
  FlagIcon,
  PaperAirplaneIcon,
} from '@heroicons/react/24/outline';
import {
  parseTrigger,
  triggerPreview,
  type ParsedTrigger,
  type TriggerEntry,
  type TriggerKind,
} from '../../lib/triggerRows';
import type { LinkedChat } from './chatToolLink';
import { useOpenChat } from './openChatContext';
import './CoreConnectionIndicator.css';

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
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-16 w-16 text-brutal-black"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={3}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
          />
        </svg>
        <span className="text-lg font-bold text-brutal-black uppercase">
          {t('chatWindow.dragDropTitle')}
        </span>
        <span className="text-sm text-brutal-black">{t('chatWindow.dragDropDesc')}</span>
      </div>
    </div>
  );
};

const KLOTSKI_VERTICES: ReadonlyArray<readonly [number, number, number]> = [
  [-1, -1, -1],
  [1, -1, -1],
  [1, 1, -1],
  [-1, 1, -1],
  [-1, -1, 1],
  [1, -1, 1],
  [1, 1, 1],
  [-1, 1, 1],
];

const KLOTSKI_NEIGHBORS: ReadonlyArray<readonly number[]> = KLOTSKI_VERTICES.map((c) =>
  KLOTSKI_VERTICES.reduce<number[]>((acc, o, j) => {
    if (Math.abs(c[0] - o[0]) + Math.abs(c[1] - o[1]) + Math.abs(c[2] - o[2]) === 2) {
      acc.push(j);
    }
    return acc;
  }, [])
);

export const LoadingIndicator: React.FC = () => {
  const { t } = useI18n();
  const [slots, setSlots] = React.useState<number[]>(() => [0, 1, 2, 3, 4, 5, 7]);
  const emptyRef = React.useRef<{ current: number; prev: number }>({ current: 6, prev: -1 });

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      if (
        document.documentElement.dataset.motion === 'reduced' ||
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      ) {
        return;
      }
      const { current: emptySlot, prev: prevEmpty } = emptyRef.current;
      const candidates = KLOTSKI_NEIGHBORS[emptySlot].filter((n) => n !== prevEmpty);
      const pickedSlot = candidates[Math.floor(Math.random() * candidates.length)];
      emptyRef.current = { current: pickedSlot, prev: emptySlot };
      setSlots((prev) => prev.map((s) => (s === pickedSlot ? emptySlot : s)));
    }, 165);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center gap-4 px-4 py-8" role="status">
      <div className="core-connection-scene" aria-hidden="true">
        <div className="core-connection-cluster">
          {slots.map((slotIndex, index) => {
            const [x, y, z] = KLOTSKI_VERTICES[slotIndex];
            const isAccent = index === 5;
            return (
              <div
                key={index}
                className={`core-connection-part${isAccent ? ' core-connection-part-accent' : ''}`}
                style={
                  {
                    '--x': x,
                    '--y': y,
                    '--z': z,
                  } as React.CSSProperties
                }
              >
                <div className="core-connection-cube">
                  {[
                    '',
                    'rotateY(180deg)',
                    'rotateY(90deg)',
                    'rotateY(-90deg)',
                    'rotateX(90deg)',
                    'rotateX(-90deg)',
                  ].map((rotation) => (
                    <div
                      key={rotation}
                      className="core-connection-face"
                      style={{ transform: `${rotation} translateZ(11px)` }}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <div className="core-connection-shadow" />
      </div>
      <span className="text-xs font-medium tracking-wide text-neutral-500 dark:text-neutral-400">
        {t('chatWindow.connecting')}
      </span>
    </div>
  );
};

const TRIGGER_ICONS: Record<TriggerKind, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  agent: ChatBubbleLeftRightIcon,
  scheduled: ClockIcon,
  goal: FlagIcon,
  other: BoltIcon,
};

function triggerSourceLabel(trigger: ParsedTrigger, t: (key: string) => string): string {
  if (trigger.kind === 'goal') return t('chatMessage.trigger.goal');
  return trigger.source || t('chatMessage.trigger.other');
}

function formatTriggerTime(timestamp: string | undefined, locale: string): string | null {
  if (!timestamp) return null;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
}

const TriggerDetails: React.FC<{ entries: TriggerEntry[] }> = ({ entries }) => {
  const { t, locale } = useI18n();
  const showState = entries.length > 1;
  return (
    <div className="mt-1.5 max-h-80 space-y-3 overflow-x-hidden overflow-y-auto overscroll-contain border-l-2 border-neutral-200 pl-3 dark:border-zinc-700">
      {entries.map((entry) => {
        const time = formatTriggerTime(entry.timestamp, locale);
        return (
          <div key={entry.index} className="min-w-0">
            {(time || showState) && (
              <div className="mb-0.5 flex items-center gap-2 text-[11px] text-neutral-400 dark:text-neutral-500">
                {time && <time dateTime={entry.timestamp}>{time}</time>}
                {showState && <span>{t(`chatMessage.trigger.state.${entry.state}`)}</span>}
              </div>
            )}
            {entry.trigger.body && (
              <div className="text-[12px] leading-relaxed text-neutral-600 dark:text-neutral-300">
                <MarkdownRenderer content={entry.trigger.body} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

/**
 * What started an agent turn without the user: another chat's message, a
 * scheduled task, goal mode or a background result. One quiet line, because
 * it is context for the reply rather than part of the conversation; repeats
 * that got no reply arrive here merged as one row.
 */
export const TriggerRow: React.FC<{ entries: TriggerEntry[] }> = ({ entries }) => {
  const { t, locale } = useI18n();
  const [expanded, setExpanded] = React.useState(false);
  const last = entries[entries.length - 1];
  if (!last) return null;

  const { trigger } = last;
  const Icon = TRIGGER_ICONS[trigger.kind];
  const preview = triggerPreview(trigger.body);
  const time = formatTriggerTime(last.timestamp, locale);
  const hasDetails = entries.some((entry) => entry.trigger.body);

  return (
    <div className="w-full max-w-3xl pl-2 md:pl-4">
      <button
        type="button"
        className="group/trigger flex w-full min-w-0 items-center gap-2 rounded-sm py-1 text-left text-[13px] text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100"
        onClick={() => hasDetails && setExpanded((value) => !value)}
        aria-expanded={hasDetails ? expanded : undefined}
        title={t(`chatMessage.trigger.kind.${trigger.kind}`)}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span
          className="shrink-0 truncate font-medium text-neutral-700 dark:text-neutral-200 max-w-[45%]"
          title={trigger.reference}
        >
          {triggerSourceLabel(trigger, t)}
        </span>
        {preview && <span className="min-w-0 truncate">{preview}</span>}
        <span className="ml-auto flex shrink-0 items-center gap-2 pl-2 text-[11px] text-neutral-400 dark:text-neutral-500">
          {entries.length > 1 && (
            <span className="font-mono">
              {t('chatMessage.trigger.count', { count: entries.length })}
            </span>
          )}
          {time && <time dateTime={last.timestamp}>{time}</time>}
          {hasDetails && (
            <DisclosureChevron expanded={expanded} className="h-3 w-3 transition-transform" />
          )}
        </span>
      </button>
      {expanded && <TriggerDetails entries={entries} />}
    </div>
  );
};

/** The trigger a reply answers, shown as one line at the top of that reply. */
export const TriggerReference: React.FC<{ entries: TriggerEntry[]; className?: string }> = ({
  entries,
  className = 'pl-2 md:pl-4',
}) => {
  const { t } = useI18n();
  const [expanded, setExpanded] = React.useState(false);
  const last = entries[entries.length - 1];
  if (!last) return null;

  const { trigger } = last;
  const Icon = TRIGGER_ICONS[trigger.kind];
  const hasDetails = entries.some((entry) => entry.trigger.body);

  return (
    <div className={`chat-trigger-reference w-full max-w-3xl ${className}`}>
      <button
        type="button"
        className="group/ref flex max-w-full min-w-0 items-center gap-1.5 py-0.5 text-left text-[12px] text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-200"
        onClick={() => hasDetails && setExpanded((value) => !value)}
        aria-expanded={hasDetails ? expanded : undefined}
        title={t(`chatMessage.trigger.kind.${trigger.kind}`)}
      >
        <ArrowTurnDownRightIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate" title={trigger.reference}>
          {t('chatMessage.trigger.repliesTo', { source: triggerSourceLabel(trigger, t) })}
        </span>
        {entries.length > 1 && (
          <span className="shrink-0 font-mono text-[11px]">
            {t('chatMessage.trigger.count', { count: entries.length })}
          </span>
        )}
        {hasDetails && (
          <DisclosureChevron
            expanded={expanded}
            className={`h-3 w-3 transition-[transform,opacity] ${expanded ? '' : 'opacity-0 group-hover/ref:opacity-100 group-focus-visible/ref:opacity-100'}`}
          />
        )}
      </button>
      {expanded && <TriggerDetails entries={entries} />}
    </div>
  );
};

/**
 * The sessions a Regent reply handed work to, under the bubble: the outgoing
 * counterpart of the TriggerReference above it. One target opens directly;
 * several fold into a count that lists them.
 */
export const DispatchReference: React.FC<{ chats: LinkedChat[] }> = ({ chats }) => {
  const { t } = useI18n();
  const openChat = useOpenChat();
  const [expanded, setExpanded] = React.useState(false);
  if (!openChat || chats.length === 0) return null;

  const single = chats.length === 1 ? chats[0] : null;
  const label = single
    ? t('chatMessage.dispatch.sentTo', { target: single.title ?? single.id })
    : t('chatMessage.dispatch.sentToMany', { count: chats.length });
  const rowClass =
    'group/ref flex max-w-full min-w-0 items-center gap-1.5 py-0.5 text-left text-[12px] text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-200';

  return (
    <div className="chat-dispatch-reference w-full max-w-3xl">
      <button
        type="button"
        className={rowClass}
        onClick={() => (single ? void openChat(single.id) : setExpanded((value) => !value))}
        aria-expanded={single ? undefined : expanded}
        title={single ? `${t('toolCallBlock.openChat')} · ${single.title ?? single.id}` : label}
      >
        <PaperAirplaneIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate">{label}</span>
        {!single && (
          <DisclosureChevron
            expanded={expanded}
            className={`h-3 w-3 transition-[transform,opacity] ${expanded ? '' : 'opacity-0 group-hover/ref:opacity-100 group-focus-visible/ref:opacity-100'}`}
          />
        )}
      </button>
      {expanded && !single && (
        <div className="mt-0.5 max-h-60 overflow-y-auto border-l-2 border-neutral-200 pl-3 dark:border-zinc-700">
          {chats.map((chat) => (
            <button
              key={chat.id}
              type="button"
              className={rowClass}
              onClick={() => void openChat(chat.id)}
              title={`${t('toolCallBlock.openChat')} · ${chat.title ?? chat.id}`}
            >
              <ChatBubbleLeftRightIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="min-w-0 truncate">{chat.title ?? chat.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

/** A single trigger row, for a trigger that arrives in the middle of a turn. */
export const SystemTriggeredMessage: React.FC<{ message: Message }> = ({ message }) => {
  const trigger = parseTrigger(message.content);
  if (!trigger.source && !trigger.body && trigger.kind === 'other') return null;
  return (
    <TriggerRow entries={[{ index: 0, trigger, timestamp: message.timestamp, state: 'replied' }]} />
  );
};

export const NoticeMessage: React.FC<{ message: Message; resolved?: boolean }> = ({
  message,
  resolved = false,
}) => {
  const { t, locale } = useI18n();
  const content = message.content?.trim() ?? '';
  if (!content) {
    return null;
  }
  const compaction = compactionNoticeDetails(message);
  if (compaction) {
    return <CompactionDivider message={message} details={compaction} resolved={resolved} />;
  }

  return (
    <div className="w-full max-w-3xl pl-2 md:pl-6">
      <div className="border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm">
        <div className="flex items-stretch">
          <div
            className="w-1.5 self-stretch bg-brutal-black dark:bg-neutral-500"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1 px-3 py-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
              {t('chatMessage.notice')}
              {message.timestamp && !Number.isNaN(Date.parse(message.timestamp)) && (
                <time dateTime={message.timestamp} className="ml-2 normal-case">
                  {new Date(message.timestamp).toLocaleString(locale)}
                </time>
              )}
            </div>
            <div className="text-sm leading-snug text-brutal-black dark:text-neutral-100">
              <MarkdownRenderer content={content} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
