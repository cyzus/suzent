/**
 * Service control for the web console.
 *
 * The desktop app reaches the same operations through Tauri `invoke`; a
 * browser has to go over HTTP, so these wrap the `/ops/*` routes. Every one of
 * them is a plain fetch — the boot-time fetch wrapper attaches the device
 * token when the console is remote.
 */

import { getApiBase } from './api';

export interface OpsServiceStatus {
  installed: boolean;
  autostart: boolean;
  running: boolean;
  ready: boolean;
  pid: number | null;
  port: number | null;
  version: string | null;
  uptimeSeconds: number | null;
  rssBytes: number | null;
  error: string | null;
  /** Whether the process answering this request is the service it describes. */
  selfManaged: boolean;
  logPath: string;
  logAvailable: boolean;
}

export interface OpsLogTail {
  path: string;
  available: boolean;
  lines: string[];
  truncated: boolean;
}

/** An error carrying the backend's machine-readable code, when it sent one. */
export class OpsError extends Error {
  constructor(
    message: string,
    readonly code: string | null,
    readonly status: number
  ) {
    super(message);
    this.name = 'OpsError';
  }
}

async function readError(response: Response): Promise<OpsError> {
  let code: string | null = null;
  let detail: string | null = null;
  try {
    const body = (await response.json()) as Record<string, unknown>;
    code = typeof body.error === 'string' ? body.error : null;
    detail = typeof body.detail === 'string' ? body.detail : null;
  } catch {
    // A proxy or a dying server can answer with something that is not JSON.
  }
  return new OpsError(detail ?? code ?? `HTTP ${response.status}`, code, response.status);
}

function toStatus(payload: Record<string, unknown>): OpsServiceStatus {
  const num = (value: unknown): number | null => (typeof value === 'number' ? value : null);
  const str = (value: unknown): string | null => (typeof value === 'string' ? value : null);
  return {
    installed: payload.installed === true,
    autostart: payload.autostart === true,
    running: payload.running === true,
    ready: payload.ready === true,
    pid: num(payload.pid),
    port: num(payload.port),
    version: str(payload.version),
    uptimeSeconds: num(payload.uptime_seconds),
    rssBytes: num(payload.rss_bytes),
    error: str(payload.error),
    selfManaged: payload.self_managed === true,
    logPath: str(payload.log_path) ?? '',
    logAvailable: payload.log_available === true,
  };
}

export async function fetchOpsStatus(signal?: AbortSignal): Promise<OpsServiceStatus> {
  const response = await fetch(`${getApiBase()}/ops/service/status`, { signal });
  if (!response.ok) throw await readError(response);
  return toStatus((await response.json()) as Record<string, unknown>);
}

export async function fetchOpsLogs(lines: number, signal?: AbortSignal): Promise<OpsLogTail> {
  const response = await fetch(`${getApiBase()}/ops/logs?lines=${lines}`, { signal });
  if (!response.ok) throw await readError(response);
  const payload = (await response.json()) as Record<string, unknown>;
  return {
    path: typeof payload.path === 'string' ? payload.path : '',
    available: payload.available === true,
    lines: Array.isArray(payload.lines) ? (payload.lines as string[]) : [],
    truncated: payload.truncated === true,
  };
}

/**
 * Restart the service.
 *
 * Resolves to null when the host deferred the restart past its own response —
 * it is about to go away, so there is no status to return and the caller has
 * to poll until it comes back.
 */
export async function restartOpsService(): Promise<OpsServiceStatus | null> {
  const response = await fetch(`${getApiBase()}/ops/service/restart`, { method: 'POST' });
  if (!response.ok) throw await readError(response);
  if (response.status === 202) return null;
  return toStatus((await response.json()) as Record<string, unknown>);
}

export async function setOpsServiceEnabled(enabled: boolean): Promise<OpsServiceStatus> {
  const response = await fetch(`${getApiBase()}/ops/service/enabled`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  if (!response.ok) throw await readError(response);
  return toStatus((await response.json()) as Record<string, unknown>);
}
