import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowPathIcon,
  BellIcon,
  ChatBubbleLeftRightIcon,
  ComputerDesktopIcon,
  QueueListIcon,
  ArrowTopRightOnSquareIcon,
  CheckIcon,
  ClockIcon,
  Cog6ToothIcon,
  HeartIcon,
  InboxStackIcon,
  LinkIcon,
  PlayIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import { isImeComposing } from '../../lib/ime';
import {
  deleteMailboxItem,
  deleteMailboxRule,
  disableHeartbeat,
  fetchCronJobs,
  fetchHeartbeatStatus,
  fetchMailboxItems,
  markMailboxRead,
  fetchMailboxRules,
  routeMailboxItem,
  triggerCronJob,
  triggerHeartbeat,
  updateCronJob,
  updateMailboxRule,
  webhookUrl,
  type CronJob,
  type HeartbeatStatus,
  type MailboxItem,
  type MailboxDelivery,
  type MailboxRule,
  type MailboxTarget,
  type WebhookUrls,
} from '../../lib/api';
import { FOCAL_CHAT_ID } from '../../lib/focalAgent';
import { formatRelativeTime } from '../../lib/chatUtils';
import { getScheduledTaskChat } from '../../lib/scheduledTaskChat';
import { BrutalIconButton } from '../BrutalButton';
import { BrutalSegmentedTabs } from '../BrutalSegmentedTabs';
import { BrutalSelect } from '../BrutalSelect';
import { RefreshButton } from '../RefreshButton';

interface RuleInstructionsProps {
  value: string | null;
  onSave: (value: string) => Promise<void>;
}

/** A rule's instructions: shown inline, edited in place, saved explicitly. */
function RuleInstructions({ value, onSave }: RuleInstructionsProps): React.ReactElement {
  const { t } = useI18n();
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (draft === null) return;
    setSaving(true);
    try {
      await onSave(draft.trim());
      setDraft(null);
    } finally {
      setSaving(false);
    }
  };

  if (draft !== null) {
    return (
      <div className="mt-2 space-y-1.5">
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (isImeComposing(e)) return;
            if (e.key === 'Escape') {
              e.preventDefault();
              setDraft(null);
            } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void save();
            }
          }}
          placeholder={t('mailboxRules.instructionsPlaceholder')}
          aria-label={t('mailboxRules.instructions')}
          rows={3}
          className="w-full border-2 border-brutal-black bg-white p-2 text-xs leading-relaxed focus:outline-none dark:border-zinc-400 dark:bg-zinc-900"
        />
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[10px] text-neutral-400">
            {t('mailboxRules.instructionsHint')}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setDraft(null)}
              className="h-7 px-2.5 font-mono text-[11px] text-neutral-600 hover:text-brutal-black dark:text-neutral-300 dark:hover:text-white"
            >
              {t('mailboxRules.cancel')}
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => void save()}
              className="h-7 border-2 border-brutal-black bg-brutal-black px-3 font-mono text-[11px] font-semibold text-white hover:bg-neutral-800 disabled:opacity-50 dark:border-zinc-200 dark:bg-zinc-200 dark:text-zinc-900"
            >
              {t('mailboxRules.save')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (value) {
    return (
      <button
        type="button"
        onClick={() => setDraft(value)}
        title={t('mailboxRules.editInstructions')}
        className="mt-1.5 block w-full border-l-2 border-brutal-yellow py-0.5 pl-2 text-left text-xs leading-relaxed text-neutral-600 hover:text-brutal-black dark:text-neutral-300 dark:hover:text-white"
      >
        <span className="font-mono text-[10px] uppercase tracking-wide text-neutral-400">
          {t('mailboxRules.instructions')}
        </span>{' '}
        <span className="line-clamp-2 whitespace-pre-wrap">{value}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setDraft('')}
      className="mt-1 font-mono text-[10px] text-neutral-400 hover:text-brutal-black dark:hover:text-white"
    >
      {t('mailboxRules.addInstructions')}
    </button>
  );
}

// GitHub's mark, from Octicons (MIT).
const GITHUB_MARK =
  'M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z';

/** What sent an inbox thread: a known mark, an icon, or the source's initials. */
function SourceMark({ item, muted }: { item: MailboxItem; muted: boolean }) {
  const KindIcon =
    item.source_kind === 'schedule'
      ? ClockIcon
      : item.source_kind === 'agent_inbox'
        ? ChatBubbleLeftRightIcon
        : item.source_kind === 'peer'
          ? ComputerDesktopIcon
          : null;
  return (
    <span
      aria-hidden="true"
      className={`flex h-8 w-8 shrink-0 items-center justify-center border ${
        muted
          ? 'border-neutral-200 text-neutral-300 dark:border-zinc-700 dark:text-zinc-600'
          : 'border-brutal-black bg-white text-brutal-black dark:border-zinc-400 dark:bg-zinc-900 dark:text-neutral-100'
      }`}
    >
      {KindIcon ? (
        <KindIcon className="h-4 w-4 stroke-2" />
      ) : item.source_name === 'github' ? (
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor">
          <path d={GITHUB_MARK} />
        </svg>
      ) : (
        <span className="font-brutal text-[11px] uppercase leading-none tracking-tight">
          {(item.source_name || '?').replace(/[^a-z0-9]/gi, '').slice(0, 2) || '?'}
        </span>
      )}
    </span>
  );
}

interface StatusPillProps {
  status: MailboxItem['route_status'];
  isUnrouted: boolean;
  targetLabel: string;
  onOpen?: () => void;
}

const PILL = 'flex h-7 w-full items-center gap-1.5 px-2 font-mono text-[11px]';

/** Where an inbox thread went, styled by what happened to it. */
function StatusPill({ status, isUnrouted, targetLabel, onOpen }: StatusPillProps) {
  const { t } = useI18n();
  if (status === 'error') {
    return (
      <span className={`${PILL} border border-brutal-red text-brutal-red`}>
        <span className="h-1.5 w-1.5 shrink-0 bg-brutal-red" />
        <span className="truncate">{t('mailboxView.status.error')}</span>
      </span>
    );
  }
  if (status === 'queued') {
    return (
      <span
        className={`${PILL} border border-amber-400 bg-amber-50 text-amber-800 dark:border-amber-500/60 dark:bg-amber-500/10 dark:text-amber-200`}
      >
        <QueueListIcon className="h-3 w-3 shrink-0 stroke-2" />
        <span className="truncate">{t('mailboxRules.queued')}</span>
      </span>
    );
  }
  if (status === 'notified') {
    return (
      <span
        className={`${PILL} border border-sky-400 bg-sky-50 text-sky-800 dark:border-sky-500/60 dark:bg-sky-500/10 dark:text-sky-200`}
      >
        <BellIcon className="h-3 w-3 shrink-0 stroke-2" />
        <span className="truncate">{t('mailboxRules.notified')}</span>
      </span>
    );
  }
  if (isUnrouted || !onOpen) {
    return (
      <span
        className={`${PILL} border border-dashed border-neutral-300 text-neutral-400 dark:border-zinc-600 dark:text-zinc-500`}
      >
        <span className="truncate">{t('mailboxView.status.unrouted')}</span>
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      title={targetLabel}
      className={`${PILL} border border-neutral-300 bg-white text-neutral-700 transition-colors hover:border-brutal-black hover:text-brutal-black dark:border-zinc-600 dark:bg-zinc-900 dark:text-neutral-200 dark:hover:border-zinc-300`}
    >
      <span
        className={`h-1.5 w-1.5 shrink-0 ${
          targetLabel === 'Regent' ? 'bg-brutal-yellow' : 'bg-neutral-400 dark:bg-zinc-500'
        }`}
      />
      <span className="truncate">{targetLabel}</span>
      <ArrowTopRightOnSquareIcon className="ml-auto h-3 w-3 shrink-0 text-neutral-400" />
    </button>
  );
}

const COMPACT_SELECT =
  '!h-7 !gap-1 !px-2 !py-0 !text-[11px] !font-medium font-mono border border-neutral-300 bg-white hover:!border-brutal-black dark:border-zinc-600 dark:bg-zinc-900 [&>svg]:!h-3 [&>svg]:!w-3 [&>svg]:shrink-0 [&>svg]:text-neutral-400';

export type MailboxTabId = 'inbox' | 'rules' | 'schedules';
type InboxCategory = 'all' | 'notifications' | 'external' | 'agent' | 'unrouted';
type HeartbeatSessionItem = NonNullable<HeartbeatStatus['active_sessions']>[number];

interface MailboxThread {
  key: string;
  category: 'external' | 'agent';
  isUnrouted: boolean;
  fromLabel: string;
  latest: MailboxItem;
  items: MailboxItem[];
  primaryChatId: string | null;
  targetLabel: string;
  isNotification: boolean;
  unreadIds: number[];
}

function plainPreview(text?: string | null): string {
  return (text || '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\[Agent message from [^\]]+\]/g, '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\*\*([^*]*)\*\*/g, '$1')
    .replace(/\*([^*]*)\*/g, '$1')
    .replace(/^#+\s*/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function compactEventLabel(sourceName: string, eventType: string): string {
  const shortEvent = eventType
    .replace(/^pull_request\b/, 'pr')
    .replace(/^workflow_run\b/, 'ci')
    .replace(/^check_run\b/, 'check')
    .replace(/^check_suite\b/, 'suite')
    .replace(/\.synchronize$/, '.sync');
  return `${sourceName}:${shortEvent}`;
}

function shortParticipantLabel(label: string): string {
  if (label.startsWith('sub_')) return 'subagent';
  if (label.includes(' · ')) {
    return label.split(' · ')[0].trim();
  }
  return label;
}

function compactSummary(text?: string | null): string {
  return plainPreview(text).replace(
    /\s+\((synchronize|opened|closed|edited|reopened|released|published|updated)\)$/i,
    ''
  );
}

function compactRelativeTime(iso: string | null | undefined, locale: string): string {
  if (!iso) return '';
  return formatRelativeTime(iso, locale)
    .replace(/\s+ago$/i, '')
    .replace(/^just now$/i, 'now');
}

interface MailboxViewProps {
  onOpenChat: (chatId: string) => void;
  onOpenSettings?: () => void;
  initialTab?: MailboxTabId;
}

export function MailboxView({
  onOpenChat,
  onOpenSettings,
  initialTab = 'inbox',
}: MailboxViewProps): React.ReactElement {
  const { t, locale } = useI18n();
  const [activeTab, setActiveTab] = useState<MailboxTabId>(initialTab);
  const [category, setCategory] = useState<InboxCategory>('all');
  const [items, setItems] = useState<MailboxItem[]>([]);
  const [rules, setRules] = useState<MailboxRule[]>([]);
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [heartbeatSessions, setHeartbeatSessions] = useState<HeartbeatSessionItem[]>([]);
  const [targets, setTargets] = useState<MailboxTarget[]>([
    { chat_id: FOCAL_CHAT_ID, label: 'Regent', kind: 'regent' },
  ]);
  const [endpoint, setEndpoint] = useState<WebhookUrls>({});
  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [itemRes, ruleRes, jobList, hbStatus] = await Promise.all([
        fetchMailboxItems({ limit: 150 }),
        fetchMailboxRules(),
        fetchCronJobs().catch(() => [] as CronJob[]),
        fetchHeartbeatStatus().catch(() => null),
      ]);
      setItems(itemRes.items);
      if (itemRes.targets?.length) setTargets(itemRes.targets);
      setEndpoint(itemRes.endpoint || {});
      setRules(ruleRes.rules);
      setJobs(jobList.filter((j) => j.source !== 'heartbeat' && j.schedule_kind !== 'webhook'));
      setHeartbeatSessions(hbStatus?.active_sessions || []);
    } catch (err) {
      console.error('Failed to load mailbox data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const threads = useMemo<MailboxThread[]>(() => {
    const map = new Map<string, MailboxItem[]>();

    for (const item of items) {
      let key: string;
      if (item.source_kind === 'agent_inbox') {
        const fromId = item.headers?.from?.startsWith('subagent-')
          ? 'subagent'
          : item.headers?.from || item.source_name || 'system';
        const toId = item.target_chat_id || 'unknown';
        const pair = [fromId, toId].sort().join('<->');
        key = `agent:${pair}`;
      } else {
        key = `ext:${item.signature}`;
      }
      const list = map.get(key);
      if (list) list.push(item);
      else map.set(key, [item]);
    }

    const result: MailboxThread[] = [];
    for (const [key, group] of map.entries()) {
      const latest = group[0];
      const isAgent = latest.source_kind === 'agent_inbox';
      const isUnrouted = latest.route_status === 'unrouted';

      let fromLabel = compactEventLabel(latest.source_name, latest.event_type);
      let primaryChatId = latest.target_chat_id;
      let targetLabel = shortParticipantLabel(latest.target_label || 'Regent');

      if (isAgent) {
        const senders = new Set(group.map((g) => shortParticipantLabel(g.source_name)));
        const receivers = new Set(
          group.map((g) => shortParticipantLabel(g.target_label || 'Regent'))
        );
        const allParticipants = Array.from(new Set([...senders, ...receivers]));
        if (allParticipants.length === 2 && senders.size > 1) {
          const other = allParticipants.find((p) => p !== 'Regent') || allParticipants[1];
          fromLabel = `Regent ⇄ ${other}`;
        } else {
          fromLabel = shortParticipantLabel(latest.source_name);
        }
        // Prefer jumping to the specific project session if one side is Regent
        const nonRegentChatId = group
          .map((g) =>
            g.target_chat_id !== FOCAL_CHAT_ID
              ? g.target_chat_id
              : g.headers?.from &&
                  g.headers.from !== FOCAL_CHAT_ID &&
                  !g.headers.from.startsWith('system')
                ? g.headers.from
                : null
          )
          .find(Boolean);
        primaryChatId = nonRegentChatId || latest.target_chat_id;
      }

      result.push({
        key,
        category: isAgent ? 'agent' : 'external',
        isUnrouted,
        fromLabel,
        latest,
        items: group,
        primaryChatId,
        targetLabel,
        isNotification: group.some((g) => g.route_status === 'notified'),
        unreadIds: group
          .filter((g) => g.route_status === 'notified' && !g.read_at)
          .map((g) => g.id),
      });
    }
    return result;
  }, [items]);

  const categoryCounts = useMemo(() => {
    let external = 0;
    let agent = 0;
    let unrouted = 0;
    let notifications = 0;
    for (const th of threads) {
      if (th.isUnrouted) unrouted++;
      if (th.isNotification) notifications++;
      if (th.category === 'agent') agent++;
      else external++;
    }
    return { all: threads.length, notifications, external, agent, unrouted };
  }, [threads]);

  const visibleThreads = useMemo(() => {
    if (category === 'all') return threads;
    if (category === 'unrouted') return threads.filter((t) => t.isUnrouted);
    if (category === 'notifications') return threads.filter((t) => t.isNotification);
    return threads.filter((t) => t.category === category);
  }, [threads, category]);

  const publicOrLocalUrl = endpoint.webhook_relay_url
    ? endpoint.webhook_relay_url
    : endpoint.webhook_path
      ? webhookUrl(endpoint.webhook_path)
      : '';

  const handleCopyEndpoint = async () => {
    if (!publicOrLocalUrl) return;
    try {
      await navigator.clipboard.writeText(publicOrLocalUrl);
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 1500);
    } catch {
      // Best-effort clipboard copy
    }
  };

  const unreadCount = threads.reduce((sum, th) => sum + th.unreadIds.length, 0);

  const markRead = async (ids?: number[]) => {
    try {
      await markMailboxRead(ids);
      await loadAll();
    } catch (err) {
      console.error('Failed to mark notifications read:', err);
    }
  };

  const toggleThread = (thread: MailboxThread) => {
    const { key } = thread;
    if (!expandedThreads.has(key) && thread.unreadIds.length > 0) {
      void markRead(thread.unreadIds);
    }
    setExpandedThreads((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleItemRouteChange = async (item: MailboxItem, selectValue: string, pinRule = true) => {
    setBusyId(item.id);
    try {
      if (selectValue === '__none__') {
        await routeMailboxItem(item.id, {
          action: 'none',
          target_chat_id: null,
          pin_rule: pinRule,
        });
      } else {
        await routeMailboxItem(item.id, {
          action: 'route',
          target_chat_id: selectValue,
          pin_rule: pinRule,
        });
      }
      await loadAll();
    } catch (err) {
      console.error('Failed to update item route:', err);
    } finally {
      setBusyId(null);
    }
  };

  const handleDeleteItem = async (id: number) => {
    try {
      await deleteMailboxItem(id);
      await loadAll();
    } catch (err) {
      console.error('Failed to delete mailbox item:', err);
    }
  };

  const ruleTarget = (rule: MailboxRule): string =>
    rule.action !== 'route'
      ? '__none__'
      : rule.target_project_id
        ? `project:${rule.target_project_id}`
        : rule.target_chat_id || '__none__';

  const deliveryOptions = (rule: MailboxRule) => {
    const digestMinutes = [15, 60, 1440];
    if (rule.delivery === 'digest' && !digestMinutes.includes(rule.digest_minutes)) {
      digestMinutes.push(rule.digest_minutes);
    }
    return [
      { value: 'wake', label: t('mailboxRules.deliveryWake') },
      ...digestMinutes.map((minutes) => ({
        value: `digest:${minutes}`,
        label:
          minutes === 60
            ? t('mailboxRules.digestHourly')
            : minutes === 1440
              ? t('mailboxRules.digestDaily')
              : t('mailboxRules.digestEvery', { minutes: String(minutes) }),
      })),
      { value: 'notify', label: t('mailboxRules.deliveryNotify') },
    ];
  };

  const saveRule = async (
    rule: MailboxRule,
    change: Partial<{
      target: string;
      delivery: MailboxDelivery;
      digest_minutes: number;
      prompt: string;
    }>
  ) => {
    const target = change.target ?? ruleTarget(rule);
    try {
      await updateMailboxRule(rule.id, {
        action: target === '__none__' ? 'none' : 'route',
        target_chat_id: target === '__none__' ? null : target,
        delivery: change.delivery ?? rule.delivery,
        digest_minutes: change.digest_minutes ?? rule.digest_minutes,
        prompt: change.prompt ?? rule.prompt,
      });
      await loadAll();
    } catch (err) {
      console.error('Failed to update rule:', err);
    }
  };

  const handleDeleteRule = async (id: number) => {
    try {
      await deleteMailboxRule(id);
      await loadAll();
    } catch (err) {
      console.error('Failed to delete rule:', err);
    }
  };

  const handleToggleJobActive = async (job: CronJob) => {
    setBusyId(`job-${job.id}`);
    try {
      await updateCronJob(job.id, { active: !job.active });
      await loadAll();
    } catch (err) {
      console.error('Failed to toggle scheduled task:', err);
    } finally {
      setBusyId(null);
    }
  };

  const handleRunJobNow = async (job: CronJob) => {
    setBusyId(`job-${job.id}`);
    try {
      await triggerCronJob(job.id);
      await loadAll();
    } catch (err) {
      console.error('Failed to trigger scheduled task:', err);
    } finally {
      setBusyId(null);
    }
  };

  const handleRunHeartbeatNow = async (chatId: string) => {
    setBusyId(`hb-${chatId}`);
    try {
      await triggerHeartbeat(chatId);
      await loadAll();
    } catch (err) {
      console.error('Failed to trigger heartbeat:', err);
    } finally {
      setBusyId(null);
    }
  };

  const handleDisableHeartbeat = async (chatId: string) => {
    setBusyId(`hb-${chatId}`);
    try {
      await disableHeartbeat(chatId);
      await loadAll();
    } catch (err) {
      console.error('Failed to disable heartbeat:', err);
    } finally {
      setBusyId(null);
    }
  };

  const routeOptionsFor = (currentChatId?: string | null, currentLabel?: string | null) => {
    const opts = targets.map((tgt) => ({
      value: tgt.chat_id,
      label: tgt.kind === 'regent' ? '→ Regent' : `→ ${tgt.label}`,
    }));
    if (currentChatId && !opts.some((o) => o.value === currentChatId)) {
      opts.push({ value: currentChatId, label: `→ ${currentLabel || currentChatId}` });
    }
    opts.push({ value: '__none__', label: 'Unrouted' });
    return opts;
  };

  const formatScheduleBadge = (job: CronJob): string => {
    if (job.schedule_kind === 'interval' && job.interval_minutes) {
      return `${job.interval_minutes}m`;
    }
    if (job.schedule_kind === 'once' && job.run_at) {
      return new Date(job.run_at).toLocaleDateString();
    }
    return job.cron_expr || 'cron';
  };

  const totalScheduledChats = jobs.length + heartbeatSessions.length;

  return (
    <div className="mx-auto h-full w-full max-w-5xl space-y-5 overflow-y-auto px-4 py-8 scrollbar-thin md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center border-2 border-brutal-black bg-brutal-yellow shadow-brutal-sm">
            <InboxStackIcon className="h-6 w-6 stroke-2 text-brutal-black" />
          </span>
          <div>
            <h2 className="font-brutal text-2xl uppercase leading-none tracking-tighter">
              {t('nav.mailbox')}
            </h2>
            <p className="mt-1 font-mono text-[11px] text-neutral-500 dark:text-neutral-400">
              {threads.length} threads · {rules.length} rules · {totalScheduledChats} scheduled
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {publicOrLocalUrl && (
            <BrutalIconButton
              onClick={() => void handleCopyEndpoint()}
              label={copiedUrl ? 'Copied webhook URL' : `Copy webhook URL (${publicOrLocalUrl})`}
            >
              {copiedUrl ? (
                <CheckIcon className="h-4 w-4 stroke-2" />
              ) : (
                <LinkIcon className="h-4 w-4 stroke-2" />
              )}
            </BrutalIconButton>
          )}
          <RefreshButton onClick={() => void loadAll()} spinning={loading} />
          {onOpenSettings && (
            <BrutalIconButton onClick={onOpenSettings} label="Automation settings">
              <Cog6ToothIcon className="h-4 w-4 stroke-2" />
            </BrutalIconButton>
          )}
        </div>
      </header>

      <BrutalSegmentedTabs<MailboxTabId>
        tabs={[
          {
            id: 'inbox',
            label: 'Inbox',
            trailing: (
              <span className="font-mono text-[10px] font-normal tabular-nums opacity-60">
                {threads.length}
              </span>
            ),
          },
          {
            id: 'rules',
            label: 'Rules',
            trailing: (
              <span className="font-mono text-[10px] font-normal tabular-nums opacity-60">
                {rules.length}
              </span>
            ),
          },
          {
            id: 'schedules',
            label: 'Scheduled',
            trailing: (
              <span className="font-mono text-[10px] font-normal tabular-nums opacity-60">
                {totalScheduledChats}
              </span>
            ),
          },
        ]}
        value={activeTab}
        onChange={setActiveTab}
        containerClassName="border-2 border-brutal-black bg-white dark:bg-zinc-800 shadow-brutal-sm"
        tabClassName="flex-1 gap-1.5 px-3 py-2 text-xs font-semibold"
      />

      {activeTab === 'inbox' && (
        <section className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-brutal-black bg-neutral-100 px-3.5 py-2 dark:bg-zinc-900">
            <h3 className="font-brutal text-xs uppercase tracking-tight">
              {t('mailboxView.messages')}
            </h3>
            <div className="flex flex-wrap items-center gap-1.5">
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={() => void markRead()}
                  className="mr-1 flex h-6 items-center gap-1 px-1.5 font-mono text-[11px] text-neutral-500 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white"
                >
                  <CheckIcon className="h-3 w-3 stroke-2" />
                  {t('mailboxView.markAllRead')}
                </button>
              )}
              {(['all', 'notifications', 'external', 'agent', 'unrouted'] as const).map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setCategory(id)}
                  aria-pressed={category === id}
                  className={`flex h-6 items-center gap-1.5 border px-2 font-mono text-[11px] transition-colors ${
                    category === id
                      ? 'border-brutal-black bg-brutal-black text-white dark:border-zinc-200 dark:bg-zinc-200 dark:text-zinc-900'
                      : 'border-neutral-300 bg-white text-neutral-600 hover:border-brutal-black hover:text-brutal-black dark:border-zinc-600 dark:bg-zinc-800 dark:text-neutral-300 dark:hover:border-zinc-300 dark:hover:text-white'
                  }`}
                >
                  {t(`mailboxView.filter.${id}`)}
                  {id === 'notifications' && unreadCount > 0 ? (
                    <span className="bg-brutal-yellow px-1 font-bold tabular-nums text-brutal-black">
                      {unreadCount}
                    </span>
                  ) : (
                    <span className="tabular-nums opacity-60">{categoryCounts[id]}</span>
                  )}
                </button>
              ))}
            </div>
          </header>

          {visibleThreads.length === 0 ? (
            <div className="flex flex-col items-center gap-2 p-12 text-center">
              <InboxStackIcon className="h-6 w-6 text-neutral-300 dark:text-zinc-600" />
              <p className="font-mono text-xs text-neutral-400">{t('mailboxView.empty')}</p>
            </div>
          ) : (
            <div className="divide-y divide-neutral-200 dark:divide-zinc-700">
              {visibleThreads.map((thread) => {
                const { latest } = thread;
                const isOpen = expandedThreads.has(thread.key);

                return (
                  <div key={thread.key}>
                    <div
                      role="button"
                      tabIndex={0}
                      aria-expanded={isOpen}
                      onClick={() => toggleThread(thread)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          toggleThread(thread);
                        }
                      }}
                      className={`grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 px-3.5 py-2.5 transition-colors hover:bg-neutral-50 sm:grid-cols-[auto_minmax(0,1fr)_8.5rem] dark:hover:bg-zinc-700/40 ${
                        isOpen ? 'bg-neutral-50 dark:bg-zinc-700/30' : ''
                      }`}
                    >
                      <SourceMark item={latest} muted={thread.isUnrouted} />

                      <div className="min-w-0">
                        <div
                          className={`flex items-center gap-1.5 truncate text-[13px] leading-snug ${
                            thread.unreadIds.length > 0 ? 'font-semibold' : ''
                          } ${
                            thread.isUnrouted
                              ? 'text-neutral-500 dark:text-neutral-400'
                              : 'font-medium text-brutal-black dark:text-neutral-100'
                          }`}
                        >
                          {thread.unreadIds.length > 0 && (
                            <span
                              className="h-2 w-2 shrink-0 bg-brutal-yellow ring-1 ring-brutal-black dark:ring-zinc-300"
                              aria-label={t('mailboxView.unread')}
                            />
                          )}
                          <span className="truncate">{compactSummary(latest.summary)}</span>
                        </div>
                        <div className="mt-0.5 flex min-w-0 items-center gap-1.5 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
                          <span className="truncate" title={thread.fromLabel}>
                            {thread.fromLabel}
                          </span>
                          {thread.items.length > 1 && (
                            <span className="shrink-0 tabular-nums">×{thread.items.length}</span>
                          )}
                          <span className="shrink-0 text-neutral-300 dark:text-zinc-600">·</span>
                          <span className="shrink-0 tabular-nums">
                            {compactRelativeTime(latest.created_at, locale)}
                          </span>
                        </div>
                      </div>

                      <div
                        className="col-span-2 flex justify-end sm:col-span-1"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <StatusPill
                          status={latest.route_status}
                          isUnrouted={thread.isUnrouted || !thread.primaryChatId}
                          targetLabel={thread.targetLabel}
                          onOpen={
                            thread.primaryChatId
                              ? () => onOpenChat(thread.primaryChatId!)
                              : undefined
                          }
                        />
                      </div>
                    </div>

                    {isOpen && (
                      <div className="border-t border-dashed border-neutral-200 bg-neutral-50/80 px-4 py-2.5 dark:border-zinc-700 dark:bg-zinc-900/60">
                        {thread.items.length > 1 ? (
                          <div className="space-y-1.5">
                            {thread.items.slice(0, 12).map((step) => (
                              <div
                                key={step.id}
                                className="flex items-baseline justify-between gap-3 border-b border-neutral-200/70 pb-1 last:border-b-0 dark:border-zinc-800"
                              >
                                <span className="w-40 shrink-0 truncate font-mono text-[10px] text-neutral-500">
                                  {step.source_name} → {step.target_label || 'Unrouted'}
                                </span>
                                <span className="min-w-0 flex-1 truncate text-[11px] text-neutral-700 dark:text-neutral-300">
                                  {plainPreview(step.summary)}
                                </span>
                                <span className="shrink-0 font-mono text-[10px] text-neutral-400">
                                  {step.created_at
                                    ? formatRelativeTime(step.created_at, locale)
                                    : ''}
                                </span>
                              </div>
                            ))}
                            {thread.primaryChatId && (
                              <div className="flex justify-end pt-1">
                                <button
                                  type="button"
                                  onClick={() => onOpenChat(thread.primaryChatId!)}
                                  className="inline-flex items-center gap-1 font-mono text-[11px] font-semibold hover:underline"
                                >
                                  Open Chat <ArrowTopRightOnSquareIcon className="h-3 w-3" />
                                </button>
                              </div>
                            )}
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <pre className="max-h-48 overflow-auto border border-neutral-300 bg-neutral-900 p-2.5 font-mono text-[11px] text-neutral-100 dark:border-zinc-700">
                              {latest.payload || latest.summary}
                            </pre>
                            <div className="flex items-center justify-end gap-3 font-mono text-[11px]">
                              {latest.source_kind !== 'agent_inbox' &&
                                !thread.isUnrouted &&
                                latest.target_chat_id && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void handleItemRouteChange(
                                        latest,
                                        latest.target_chat_id!,
                                        false
                                      )
                                    }
                                    className="inline-flex items-center gap-1 text-neutral-600 hover:text-brutal-black dark:text-neutral-400 dark:hover:text-white"
                                  >
                                    <ArrowPathIcon className="h-3 w-3" /> Replay
                                  </button>
                                )}
                              <button
                                type="button"
                                onClick={() => void handleDeleteItem(latest.id)}
                                className="inline-flex items-center gap-1 text-neutral-500 hover:text-brutal-red"
                              >
                                <TrashIcon className="h-3 w-3" /> Delete
                              </button>
                              {thread.primaryChatId && (
                                <button
                                  type="button"
                                  onClick={() => onOpenChat(thread.primaryChatId!)}
                                  className="inline-flex items-center gap-1 font-semibold hover:underline"
                                >
                                  Open Chat <ArrowTopRightOnSquareIcon className="h-3 w-3" />
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {activeTab === 'rules' && (
        <section className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
          <header className="flex items-center justify-between border-b-2 border-brutal-black bg-neutral-100 px-3.5 py-2 dark:bg-zinc-900">
            <h3 className="font-brutal text-xs uppercase tracking-tight">Routing Rules</h3>
            <span className="font-mono text-[10px] text-neutral-500">{rules.length}</span>
          </header>

          {rules.length === 0 ? (
            <div className="p-10 text-center">
              <p className="font-mono text-xs text-neutral-400">No rules</p>
            </div>
          ) : (
            <div className="divide-y divide-neutral-200 dark:divide-zinc-700">
              {rules.map((rule) => {
                const target = ruleTarget(rule);
                const routes = target !== '__none__';

                const takesInstructions = routes && rule.delivery !== 'notify';
                const deliveryValue =
                  rule.delivery === 'digest' ? `digest:${rule.digest_minutes}` : rule.delivery;

                return (
                  <div
                    key={rule.id}
                    className="px-3.5 py-2 hover:bg-neutral-50 dark:hover:bg-zinc-700/40"
                  >
                    <div className="grid grid-cols-1 items-center gap-x-2 gap-y-1.5 sm:grid-cols-[minmax(0,1fr)_11rem_9.5rem_1.75rem]">
                      <div className="min-w-0" title={rule.signature}>
                        <div className="truncate font-mono text-xs font-semibold text-brutal-black dark:text-neutral-100">
                          {rule.name || rule.signature}
                        </div>
                        <div className="truncate font-mono text-[10px] text-neutral-500">
                          {rule.origin === 'pinned'
                            ? t('mailboxRules.originPinned')
                            : t('mailboxRules.originLearned')}
                          {' · '}
                          {t('mailboxRules.hits', { count: String(rule.hit_count) })}
                        </div>
                      </div>

                      <BrutalSelect
                        value={target}
                        ariaLabel={t('mailboxRules.targetLabel')}
                        variant="ghost"
                        options={routeOptionsFor(
                          target === '__none__' ? null : target,
                          rule.target_label
                        )}
                        onChange={(val) => void saveRule(rule, { target: val })}
                        buttonClassName={COMPACT_SELECT}
                      />

                      {routes ? (
                        <BrutalSelect
                          value={deliveryValue}
                          ariaLabel={t('mailboxRules.deliveryLabel')}
                          variant="ghost"
                          options={deliveryOptions(rule)}
                          onChange={(val) => {
                            const [delivery, minutes] = val.split(':');
                            void saveRule(rule, {
                              delivery: delivery as MailboxDelivery,
                              ...(minutes ? { digest_minutes: Number(minutes) } : {}),
                            });
                          }}
                          buttonClassName={COMPACT_SELECT}
                        />
                      ) : (
                        <span className="hidden text-center font-mono text-[11px] text-neutral-300 sm:block dark:text-zinc-600">
                          —
                        </span>
                      )}

                      <button
                        type="button"
                        onClick={() => void handleDeleteRule(rule.id)}
                        title={t('mailboxRules.delete')}
                        className="flex h-7 w-7 items-center justify-center text-neutral-400 hover:text-brutal-red"
                      >
                        <TrashIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>

                    {takesInstructions && (
                      <RuleInstructions
                        value={rule.prompt}
                        onSave={(prompt) => saveRule(rule, { prompt })}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {activeTab === 'schedules' && (
        <section className="border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
          <header className="flex items-center justify-between border-b-2 border-brutal-black bg-neutral-100 px-3.5 py-2 dark:bg-zinc-900">
            <h3 className="font-brutal text-xs uppercase tracking-tight">Scheduled Chats</h3>
            <span className="font-mono text-[10px] text-neutral-500">{totalScheduledChats}</span>
          </header>

          {totalScheduledChats === 0 ? (
            <div className="p-10 text-center">
              <p className="font-mono text-xs text-neutral-400">No scheduled chats</p>
            </div>
          ) : (
            <div className="divide-y divide-neutral-200 dark:divide-zinc-700">
              {jobs.map((job) => {
                const { chatId } = getScheduledTaskChat(job);
                const subtitle = plainPreview(job.last_error || job.last_result || job.prompt);

                return (
                  <div
                    key={`job-${job.id}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => onOpenChat(chatId)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onOpenChat(chatId);
                      }
                    }}
                    className={`group flex cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5 transition-colors hover:bg-neutral-50 dark:hover:bg-zinc-700/50 ${
                      !job.active ? 'opacity-55' : ''
                    }`}
                  >
                    <div className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:gap-3">
                      <div className="flex shrink-0 items-center gap-2">
                        <ClockIcon className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
                        <span className="font-mono text-xs font-semibold group-hover:underline">
                          {job.name}
                        </span>
                        {job.unread_count > 0 && (
                          <span className="border border-brutal-black bg-brutal-yellow px-1 font-mono text-[10px] text-brutal-black">
                            {job.unread_count}
                          </span>
                        )}
                        {job.is_running && (
                          <span className="h-2 w-2 rounded-full bg-brutal-blue animate-pulse" />
                        )}
                      </div>
                      {subtitle && (
                        <span className="min-w-0 truncate text-[11px] text-neutral-500 dark:text-neutral-400">
                          {subtitle}
                        </span>
                      )}
                    </div>

                    <div
                      className="flex shrink-0 items-center gap-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <span className="font-mono text-[10px] text-neutral-400">
                        {formatScheduleBadge(job)}
                      </span>
                      <button
                        type="button"
                        onClick={() => void handleToggleJobActive(job)}
                        title={job.active ? 'Pause' : 'Resume'}
                        disabled={busyId === `job-${job.id}`}
                        className={`flex h-4 w-7 items-center border border-brutal-black p-0.5 transition-colors ${
                          job.active
                            ? 'justify-end bg-brutal-green'
                            : 'justify-start bg-neutral-200 dark:bg-zinc-700'
                        }`}
                      >
                        <span className="h-2.5 w-2.5 border border-brutal-black bg-white" />
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleRunJobNow(job)}
                        title="Run now"
                        disabled={busyId === `job-${job.id}` || job.is_running}
                        className="p-1 text-neutral-400 hover:text-brutal-black dark:hover:text-white"
                      >
                        <PlayIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}

              {heartbeatSessions.map((session) => (
                <div
                  key={`hb-${session.chat_id}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => onOpenChat(session.chat_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onOpenChat(session.chat_id);
                    }
                  }}
                  className="group flex cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5 transition-colors hover:bg-neutral-50 dark:hover:bg-zinc-700/50"
                >
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <HeartIcon className="h-3.5 w-3.5 shrink-0 text-neutral-400" />
                    <span className="truncate font-mono text-xs font-semibold group-hover:underline">
                      {session.title || session.chat_id}
                    </span>
                    {session.unread_count > 0 && (
                      <span className="border border-brutal-black bg-brutal-yellow px-1 font-mono text-[10px] text-brutal-black">
                        {session.unread_count}
                      </span>
                    )}
                    {session.is_running && (
                      <span className="h-2 w-2 rounded-full bg-brutal-blue animate-pulse" />
                    )}
                  </div>

                  <div
                    className="flex shrink-0 items-center gap-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className="font-mono text-[10px] text-neutral-400">
                      {session.interval_minutes}m
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleRunHeartbeatNow(session.chat_id)}
                      title="Check-in now"
                      disabled={busyId === `hb-${session.chat_id}` || session.is_running}
                      className="p-1 text-neutral-400 hover:text-brutal-black dark:hover:text-white"
                    >
                      <PlayIcon className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDisableHeartbeat(session.chat_id)}
                      title="Disable heartbeat"
                      disabled={busyId === `hb-${session.chat_id}`}
                      className="p-1 text-neutral-400 hover:text-brutal-red"
                    >
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
