import { useChatCoreStore } from './useChatStore';
import { useContextUsageStore } from './useContextUsageStore';
import { selectContextLimit } from '../lib/contextLimit';

export function useContextUsageStats(chatId: string | null | undefined) {
  const { config, backendConfig } = useChatCoreStore();
  const usage = useContextUsageStore((state) => (chatId ? state.usageByChatId[chatId] : undefined));
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
  // The provider-reported count, which headline numbers use; the breakdown is an estimate.
  const measured = usage ? (usage.context_tokens ?? usage.total_tokens ?? 0) : null;
  const measuredPercent =
    measured != null && limit ? Math.min(100, (measured / limit) * 100) : null;
  // Reserve is a policy budget, not occupied context; it shrinks at capacity.
  const reserveBudget = breakdown
    ? breakdown.reserve_tokens * ((limit ?? 0) / (usage?.context_limit || limit || 1))
    : 0;
  const reserve = known && breakdown ? Math.min(reserveBudget, Math.max(0, limit! - used)) : 0;
  const free = known ? Math.max(0, limit! - used - reserve) : 0;
  const categories = [...(breakdown?.categories ?? [])].sort((a, b) => b.tokens - a.tokens);
  const denominator = Math.max(limit ?? 0, used + reserve, 1);
  return {
    usage,
    breakdown,
    known,
    limit,
    used,
    percent,
    measured,
    measuredPercent,
    reserve,
    free,
    categories,
    denominator,
  };
}
