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
  skipped?: string[];
}

export interface DataImportPreview {
  archive_path: string;
  valid: boolean;
  entries: string[];
}

export interface DataImportResult {
  archive_path: string;
  data_dir: string;
  backup_path: string;
  restored_entries: string[];
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${getApiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const payload = await res.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      // Keep the HTTP status text when the backend did not return JSON.
    }
    throw new Error(`Request failed: ${detail}`);
  }
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

export function previewImportData(archive: string): Promise<DataImportPreview> {
  return postJson<DataImportPreview>('/data/import/dry-run', { archive });
}

export function importData(archive: string): Promise<DataImportResult> {
  return postJson<DataImportResult>('/data/import', { archive });
}

export function syncPush(target: string): Promise<DataExportResult> {
  return postJson<DataExportResult>('/data/sync/push', { target });
}

export function previewSyncPull(target: string): Promise<DataImportPreview> {
  return postJson<DataImportPreview>('/data/sync/pull', { target, dry_run: true });
}

export function syncPull(target: string): Promise<DataImportResult> {
  return postJson<DataImportResult>('/data/sync/pull', { target });
}
