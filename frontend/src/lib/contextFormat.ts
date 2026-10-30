export function formatTokens(value: number): string {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(
    value
  );
}

// Keep a sliver visible rather than rounding it away to a flat "0%".
export function formatPercent(value: number): string {
  return value >= 10 || value === 0 ? `${Math.round(value)}%` : `${value.toFixed(1)}%`;
}

export function usageBarColor(percent: number): string {
  if (percent >= 80) return 'bg-brutal-red';
  if (percent >= 60) return 'bg-brutal-yellow';
  return 'bg-neutral-400 dark:bg-neutral-500';
}
