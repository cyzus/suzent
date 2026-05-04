import { getApiBase } from './api';

export interface DataStatus {
  data_dir: string;
  runtime_dir: string;
  cache_dir: string;
  exists: boolean;
  portable_entries: string[];
}

export interface DataExportResult {
  output_path: string;
  included: string[];
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Request failed: ${res.statusText}`);
  return res.json();
}

export async function fetchDataStatus(): Promise<DataStatus> {
  const res = await fetch(`${getApiBase()}/data/status`);
  if (!res.ok) throw new Error(`Failed to fetch data status: ${res.statusText}`);
  return res.json();
}

export function exportData(output?: string): Promise<DataExportResult> {
  return postJson<DataExportResult>('/data/export', output ? { output } : {});
}

export function syncPush(target: string): Promise<DataExportResult> {
  return postJson<DataExportResult>('/data/sync/push', { target });
}
