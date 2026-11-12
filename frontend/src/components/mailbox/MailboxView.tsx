import React, { useCallback, useEffect, useState } from 'react';
import {
  ArrowPathIcon,
  CheckIcon,
  ClockIcon,
  CodeBracketIcon,
  Cog6ToothIcon,
  HeartIcon,
  InboxStackIcon,
  LinkIcon,
  PlayIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';

import { useI18n } from '../../i18n';
import {
  deleteMailboxItem,
  deleteMailboxRule,
  disableHeartbeat,
  fetchCronJobs,
  fetchHeartbeatStatus,
  fetchMailboxItems,
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

export type MailboxTabId = 'inbox' | 'rules' | 'schedules';
type InboxFilter = 'all' | 'routed' | 'unrouted';
type HeartbeatSessionItem = NonNullable<HeartbeatStatus['active_sessions']>[number];

function plainPreview(text?: string | null): string {
  return (text || '')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\*\*([^*]*)\*\*/g, '$1')
    .replace(/\*([^*]*)\*/g, '$1')
    .replace(/^#+\s*/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
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
  const [filter, setFilter] = useState<InboxFilter>('all');
  const [items, setItems] = useState<MailboxItem[]>([]);
  const [counts, setCounts] = useState<{ all: number; routed: number; unrouted: number }>({
    all: 0,
    routed: 0,
    unrouted: 0,
  });
  const [rules, setRules] = useState<MailboxRule[]>([]);
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [heartbeatSessions, setHeartbeatSessions] = useState<HeartbeatSessionItem[]>([]);
  const [targets, setTargets] = useState<MailboxTarget[]>([
    { chat_id: FOCAL_CHAT_ID, label: 'Regent', kind: 'regent' },
  ]);
  const [endpoint, setEndpoint] = useState<WebhookUrls>({});
  const [expandedPayloads, setExpandedPayloads] = useState<Set<number>>(new Set());
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [itemRes, ruleRes, jobList, hbStatus] = await Promise.all([
        fetchMailboxItems({ route_status: filter }),
        fetchMailboxRules(),
        fetchCronJobs().catch(() => [] as CronJob[]),
        fetchHeartbeatStatus().catch(() => null),
      ]);
      setItems(itemRes.items);
      setCounts(itemRes.counts);
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
  }, [filter]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

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

  const togglePayload = (id: number) => {
    setExpandedPayloads((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleItemRouteChange = async (
    item: MailboxItem,
    selectValue: string,
    pinRule = true
  ) => {
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

  const handleRuleChange = async (rule: MailboxRule, selectValue: string) => {
    try {
      if (selectValue === '__none__') {
        await updateMailboxRule(rule.id, { action: 'none', target_chat_id: null });
      } else {
        await updateMailboxRule(rule.id, {
          action: 'route',
          target_chat_id: selectValue,
        });
      }
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
      label: tgt.kind === 'regent' ? 'Regent' : tgt.label,
    }));
    if (currentChatId && !opts.some((o) => o.value === currentChatId)) {
      opts.push({ value: currentChatId, label: currentLabel || currentChatId });
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
              {counts.all} events · {rules.length} rules · {totalScheduledChats} scheduled
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
                {counts.all}
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
        <div className="space-y-3">
          {counts.all > 0 && (
            <div className="flex items-center">
              <BrutalSegmentedTabs<InboxFilter>
                tabs={[
                  { id: 'all', label: `All (${counts.all})` },
                  { id: 'routed', label: `Routed (${counts.routed})` },
                  { id: 'unrouted', label: `Unrouted (${counts.unrouted})` },
                ]}
                value={filter}
                onChange={setFilter}
                containerClassName="border-2 border-brutal-black bg-white dark:bg-zinc-800"
                tabClassName="px-3 py-1 text-xs font-medium"
              />
            </div>
          )}

          {items.length === 0 ? (
            <div className="border-2 border-brutal-black bg-white p-10 text-center shadow-brutal-sm dark:bg-zinc-800">
              <p className="font-mono text-xs text-neutral-400">No events</p>
            </div>
          ) : (
            <section className="divide-y-2 divide-brutal-black border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
              {items.map((item) => {
                const isRouted = item.route_status === 'routed' && Boolean(item.target_chat_id);
                const selectVal = isRouted ? item.target_chat_id! : '__none__';
                const isPayloadOpen = expandedPayloads.has(item.id);

                return (
                  <div
                    key={item.id}
                    className={`group px-3.5 py-2.5 transition-colors hover:bg-neutral-50 dark:hover:bg-zinc-700/60 ${
                      !isRouted ? 'opacity-65' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex min-w-0 flex-1 items-center gap-2.5">
                        <span className="shrink-0 border border-neutral-300 bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600 dark:border-zinc-600 dark:bg-zinc-900 dark:text-neutral-300">
                          {item.source_name}:{item.event_type}
                        </span>
                        <button
                          type="button"
                          disabled={!isRouted}
                          onClick={() =>
                            isRouted && item.target_chat_id && onOpenChat(item.target_chat_id)
                          }
                          className={`min-w-0 flex-1 truncate text-left text-xs ${
                            isRouted
                              ? 'cursor-pointer font-medium hover:underline'
                              : 'cursor-default text-neutral-500'
                          }`}
                        >
                          {plainPreview(item.summary)}
                        </button>
                      </div>

                      <div className="flex shrink-0 items-center gap-2">
                        <span className="font-mono text-[10px] text-neutral-400">
                          {item.created_at ? formatRelativeTime(item.created_at, locale) : ''}
                        </span>
                        <div className="w-36">
                          <BrutalSelect
                            value={selectVal}
                            ariaLabel="Route target"
                            variant="ghost"
                            disabled={busyId === item.id}
                            options={routeOptionsFor(item.target_chat_id, item.target_label)}
                            onChange={(val) => void handleItemRouteChange(item, val, true)}
                            buttonClassName="border border-neutral-300 dark:border-zinc-600 py-0.5 px-2 text-[11px] font-mono bg-neutral-50 dark:bg-zinc-900"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => togglePayload(item.id)}
                          title="Payload"
                          className="p-1 text-neutral-400 hover:text-brutal-black dark:hover:text-white"
                        >
                          <CodeBracketIcon className="h-3.5 w-3.5" />
                        </button>
                        {isRouted && item.target_chat_id && (
                          <button
                            type="button"
                            onClick={() =>
                              void handleItemRouteChange(item, item.target_chat_id!, false)
                            }
                            title="Replay"
                            disabled={busyId === item.id}
                            className="p-1 text-neutral-400 hover:text-brutal-black dark:hover:text-white"
                          >
                            <ArrowPathIcon className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => void handleDeleteItem(item.id)}
                          title="Delete"
                          className="p-1 text-neutral-400 hover:text-brutal-red"
                        >
                          <TrashIcon className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>

                    {isPayloadOpen && (
                      <pre className="mt-2 max-h-56 overflow-auto border border-neutral-300 bg-neutral-900 p-2.5 font-mono text-[11px] text-neutral-100 dark:border-zinc-700">
                        {item.payload || '(empty)'}
                      </pre>
                    )}
                  </div>
                );
              })}
            </section>
          )}
        </div>
      )}

      {activeTab === 'rules' && (
        <div>
          {rules.length === 0 ? (
            <div className="border-2 border-brutal-black bg-white p-10 text-center shadow-brutal-sm dark:bg-zinc-800">
              <p className="font-mono text-xs text-neutral-400">No rules</p>
            </div>
          ) : (
            <section className="divide-y-2 divide-brutal-black border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
              {rules.map((rule) => {
                const isRouted = rule.action === 'route' && Boolean(rule.target_chat_id);
                const selectVal = isRouted ? rule.target_chat_id! : '__none__';

                return (
                  <div
                    key={rule.id}
                    className="flex items-center justify-between gap-3 px-3.5 py-2.5 hover:bg-neutral-50 dark:hover:bg-zinc-700/60"
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-2.5">
                      <span className="truncate font-mono text-xs">
                        {rule.signature}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] text-neutral-400">
                        {rule.origin} · {rule.hit_count}
                      </span>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <div className="w-36">
                        <BrutalSelect
                          value={selectVal}
                          ariaLabel="Rule target"
                          variant="ghost"
                          options={routeOptionsFor(rule.target_chat_id, rule.target_label)}
                          onChange={(val) => void handleRuleChange(rule, val)}
                          buttonClassName="border border-neutral-300 dark:border-zinc-600 py-0.5 px-2 text-[11px] font-mono bg-neutral-50 dark:bg-zinc-900"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => void handleDeleteRule(rule.id)}
                        title="Delete rule"
                        className="p-1 text-neutral-400 hover:text-brutal-red"
                      >
                        <TrashIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </section>
          )}
        </div>
      )}

      {activeTab === 'schedules' && (
        <div>
          {totalScheduledChats === 0 ? (
            <div className="border-2 border-brutal-black bg-white p-10 text-center shadow-brutal-sm dark:bg-zinc-800">
              <p className="font-mono text-xs text-neutral-400">No scheduled chats</p>
            </div>
          ) : (
            <section className="divide-y-2 divide-brutal-black border-2 border-brutal-black bg-white shadow-brutal-sm dark:bg-zinc-800">
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
                    className={`group flex cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5 transition-colors hover:bg-neutral-50 dark:hover:bg-zinc-700/60 ${
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
                        className={`h-4 w-7 flex items-center border border-brutal-black p-0.5 transition-colors ${
                          job.active
                            ? 'bg-brutal-green justify-end'
                            : 'bg-neutral-200 dark:bg-zinc-700 justify-start'
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
                  className="group flex cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5 transition-colors hover:bg-neutral-50 dark:hover:bg-zinc-700/60"
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
            </section>
          )}
        </div>
      )}
    </div>
  );
}
