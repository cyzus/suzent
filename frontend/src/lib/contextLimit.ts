/**
 * Which context budget the usage panel draws its percentage against.
 *
 * The budget belongs to a model, not to the app: a 1M-token model and a 128k one
 * are at very different fractions of full with the same conversation in them.
 */
export function selectContextLimit({
  selectedModel,
  contextWindows,
  turnLimit,
  fallback,
}: {
  /** Model currently chosen in the selector (a provider-prefixed id). */
  selectedModel?: string;
  /** Per-model budgets from the backend config listing. */
  contextWindows?: Record<string, number>;
  /** Limit the last turn reported alongside its usage. */
  turnLimit?: number | null;
  /** Backend-wide default, for a model nothing else knows about. */
  fallback?: number;
}): number | undefined {
  // Selector first: switching models has to move the maximum immediately, and
  // the last turn's limit belongs to whichever model ran that turn.
  const selected = selectedModel ? contextWindows?.[selectedModel] : undefined;
  return selected || turnLimit || fallback || undefined;
}
