import { getApiBase, refreshAllProviderModels, type RefreshProviderModelsResponse } from './api';

/**
 * Provider model discovery calls every configured provider's API and rewrites
 * the model registry, but the composer that triggers it remounts on every chat
 * switch. One app-wide record keeps that to once per backend per TTL.
 */
export const AUTO_REFRESH_TTL_MS = 15 * 60 * 1000;

interface RefreshRecord {
  apiBase: string;
  startedAt: number;
  result: Promise<RefreshProviderModelsResponse>;
  settled: boolean;
  // A later /config listing reads the same enabled-model table the refresh
  // wrote, so once it lands the refresh result adds nothing and may be stale.
  superseded: boolean;
}

let record: RefreshRecord | null = null;

function start(apiBase: string): RefreshRecord {
  const next: RefreshRecord = {
    apiBase,
    startedAt: Date.now(),
    result: refreshAllProviderModels(),
    settled: false,
    superseded: false,
  };
  next.result = next.result.then((result) => {
    next.settled = true;
    if (!result.success && record === next) record = null;
    return result;
  });
  record = next;
  return next;
}

/** Run discovery unless a recent refresh for this backend already ran.
 * Returns null when the backend config listing is already at least as fresh. */
export function autoRefreshProviderModels(): Promise<RefreshProviderModelsResponse> | null {
  const apiBase = getApiBase();
  const fresh =
    record !== null &&
    record.apiBase === apiBase &&
    Date.now() - record.startedAt < AUTO_REFRESH_TTL_MS;
  if (!fresh) return start(apiBase).result;
  return record!.superseded ? null : record!.result;
}

/** Explicit user refresh: always hits providers, and resets the TTL. */
export function forceRefreshProviderModels(): Promise<RefreshProviderModelsResponse> {
  const apiBase = getApiBase();
  if (record && record.apiBase === apiBase && !record.settled) return record.result;
  return start(apiBase).result;
}

/** Call after a successful /config fetch. */
export function markProviderModelsSuperseded(): void {
  if (record?.settled) record.superseded = true;
}

export function resetProviderModelsRefreshForTests(): void {
  record = null;
}
