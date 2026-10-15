import { ChevronRightIcon } from '@heroicons/react/24/outline';
import { useChatCoreStore } from '../../hooks/useChatStore';
import { useContextUsageStore } from '../../hooks/useContextUsageStore';
import { useI18n } from '../../i18n';
import { selectContextLimit } from '../../lib/contextLimit';
import type { ContextCategory, ContextCategoryId } from '../../types/contextUsage';

const COLORS: Record<ContextCategoryId, string> = {
  messages: 'bg-brutal-blue',
  tool_results: 'bg-violet-400',
  system_tools: 'bg-orange-400',
  mcp_tools: 'bg-brutal-green',
  skills: 'bg-brutal-yellow',
  system_prompt: 'bg-neutral-500',
  memory: 'bg-pink-300',
  repository: 'bg-cyan-300',
  other: 'bg-neutral-400',
};
const GRID = 'grid grid-cols-[minmax(0,1fr)_auto_3rem] items-center gap-2 text-xs tabular-nums';

function formatTokens(value: number): string {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value
  );
}

function CategoryRow({
  row,
  limit,
  deferred = false,
}: {
  row: ContextCategory;
  limit?: number;
  deferred?: boolean;
}): JSX.Element {
  const { t } = useI18n();
  const expandable =
    row.items.length > 0 &&
    ['system_tools', 'mcp_tools', 'skills', 'memory', 'repository'].includes(row.id);
  const content = (
    <>
      <span className="flex min-w-0 items-center gap-2 text-neutral-600 dark:text-neutral-300">
        <span
          aria-hidden="true"
          className={`h-3 w-3 shrink-0 border border-brutal-black ${COLORS[row.id]}`}
        />
        <span>
          {t(`contextPanel.categories.${row.id}`)}
          {deferred ? ` ${t('contextPanel.deferred')}` : ''}
        </span>
        {expandable && (
          <ChevronRightIcon
            aria-hidden="true"
            className="h-3 w-3 shrink-0 transition-transform group-open:rotate-90"
            strokeWidth={2.5}
          />
        )}
      </span>
      <span className="font-mono text-neutral-500 dark:text-neutral-400">
        ≈{formatTokens(row.tokens)}
      </span>
      <span className="text-right font-mono text-neutral-900 dark:text-neutral-100">
        {!deferred && limit ? `${((row.tokens / limit) * 100).toFixed(1)}%` : '—'}
      </span>
    </>
  );
  if (!expandable) return <div className={`${GRID} py-1.5`}>{content}</div>;
  return (
    <details className="group">
      <summary
        className={`${GRID} cursor-pointer list-none py-1.5 hover:bg-neutral-100 dark:hover:bg-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brutal-blue [&::-webkit-details-marker]:hidden`}
      >
        {content}
      </summary>
      <ul className="my-2 ml-1.5 space-y-2 border-l-2 border-brutal-black/20 pl-4 font-mono text-[10px] dark:border-zinc-600">
        {row.items.map((item) => {
          const key = `contextPanel.sources.${item.name}`;
          const translated = t(key);
          return (
            <li
              key={item.name}
              className="flex items-baseline justify-between gap-3 text-neutral-500 dark:text-neutral-400"
            >
              <span className="min-w-0 break-words">
                {translated === key ? item.name : translated}
              </span>
              <span className="shrink-0 tabular-nums">≈{formatTokens(item.tokens)}</span>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

export function ContextUsageSummary({ chatId }: { chatId: string }): JSX.Element {
  const { t } = useI18n();
  const { config, backendConfig } = useChatCoreStore();
  const usage = useContextUsageStore((state) => state.usageByChatId[chatId]);
  const limit = selectContextLimit({
    selectedModel:
      config?.model || backendConfig?.userPreferences?.model || backendConfig?.models?.[0],
    contextWindows: backendConfig?.contextWindows,
    turnLimit: usage?.context_limit,
    fallback: backendConfig?.maxContextTokens,
  });
  const breakdown = usage?.context_breakdown;
  const tokens = breakdown?.estimated_tokens ?? usage?.context_tokens;
  const known = tokens != null && Number.isFinite(tokens) && tokens >= 0 && !!limit && limit > 0;
  const used = known ? tokens : 0;
  const percent = known ? (used / limit!) * 100 : 0;
  // Reserve is a policy budget, not occupied context; it shrinks at capacity.
  const reserveBudget = breakdown
    ? breakdown.reserve_tokens * ((limit ?? 0) / (usage?.context_limit || limit || 1))
    : 0;
  const reserve = known && breakdown ? Math.min(reserveBudget, Math.max(0, limit! - used)) : 0;
  const free = known ? Math.max(0, limit! - used - reserve) : 0;
  const categories = [...(breakdown?.categories ?? [])].sort((a, b) => b.tokens - a.tokens);
  const denominator = Math.max(limit ?? 0, used + reserve, 1);
  const extraRows = [
    ...(!breakdown ? [{ key: 'usedContext', tokens: used, color: COLORS.messages }] : []),
    ...(breakdown ? [{ key: 'reserve', tokens: reserve, color: 'bg-neutral-400' }] : []),
    { key: 'freeSpace', tokens: free, color: 'bg-neutral-100 dark:bg-zinc-700' },
  ];

  return (
    <section
      aria-label={t('contextPanel.usage')}
      className="space-y-3 border-2 border-brutal-black bg-white p-3 shadow-brutal-sm dark:bg-zinc-800"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 tabular-nums">
        <span className="font-brutal text-lg uppercase text-neutral-900 dark:text-neutral-100">
          {known
            ? `≈ ${t('contextPanel.percentUsed', { percent: Math.round(percent) })}`
            : t('contextPanel.noUsage')}
        </span>
        <span className="font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
          {known ? `≈${formatTokens(used)} / ${formatTokens(limit!)}` : '—'}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={t('contextPanel.usage')}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={known ? Math.min(percent, 100) : undefined}
        className="flex h-3 overflow-hidden border-2 border-brutal-black bg-neutral-100 dark:bg-zinc-700"
      >
        {(breakdown ? categories : [{ id: 'messages' as const, tokens: used }]).map((row) => (
          <div
            key={row.id}
            title={t(`contextPanel.categories.${row.id}`)}
            className={`h-full shrink-0 ${COLORS[row.id]}`}
            style={{
              width: `${(row.tokens / denominator) * 100}%`,
            }}
          />
        ))}
        {reserve > 0 && (
          <div
            title={t('contextPanel.reserve')}
            className="h-full shrink-0 bg-neutral-400"
            style={{ width: `${(reserve / denominator) * 100}%` }}
          />
        )}
      </div>
      <div className="space-y-0.5">
        {categories.map((row) => (
          <CategoryRow key={row.id} row={row} limit={limit} />
        ))}
        {extraRows.map((row) => (
          <div key={row.key} className={`${GRID} py-1.5`}>
            <span className="flex items-center gap-2 text-neutral-600 dark:text-neutral-300">
              <span
                aria-hidden="true"
                className={`h-3 w-3 shrink-0 border border-brutal-black ${row.color}`}
              />
              {t(`contextPanel.${row.key}`)}
            </span>
            <span className="font-mono text-neutral-500 dark:text-neutral-400">
              {known ? formatTokens(row.tokens) : '—'}
            </span>
            <span className="text-right font-mono text-neutral-900 dark:text-neutral-100">
              {known ? `${((row.tokens / limit!) * 100).toFixed(1)}%` : '—'}
            </span>
          </div>
        ))}
      </div>
      {!!breakdown?.deferred.length && (
        <div className="space-y-0.5 border-t-2 border-brutal-black/10 pt-2 dark:border-zinc-600">
          {breakdown.deferred.map((row) => (
            <CategoryRow key={row.id} row={row} deferred />
          ))}
        </div>
      )}
      <p className="border-t border-brutal-black/10 pt-3 font-mono text-[10px] leading-relaxed text-neutral-500 dark:border-zinc-600 dark:text-neutral-400">
        {t(breakdown ? 'contextPanel.estimateNote' : 'contextPanel.breakdownUnavailable')}
      </p>
      {breakdown?.has_unmeasured_media && (
        <p className="font-mono text-[10px] text-amber-600 dark:text-amber-400">
          {t('contextPanel.unmeasured')}
        </p>
      )}
      {breakdown?.measured_input_tokens != null && (
        <p className="flex justify-between gap-3 font-mono text-[10px] text-neutral-500 dark:text-neutral-400">
          <span>{t('contextPanel.measuredInput')}</span>
          <span className="tabular-nums">{formatTokens(breakdown.measured_input_tokens)}</span>
        </p>
      )}
    </section>
  );
}
