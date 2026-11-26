/** Talking to a backend's /health endpoint and deciding whether it is ours. */

import fs from 'node:fs';
import path from 'node:path';

import type { Layout } from './layout';

export interface HealthPayload {
  app?: unknown;
  status?: unknown;
  version?: unknown;
  source_root?: unknown;
}

export const SERVICE_PORT = 25314;

export async function fetchHealth(port: number, timeoutMs = 1000): Promise<HealthPayload | null> {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/health`, {
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return null;
    const payload: unknown = await response.json();
    return payload && typeof payload === 'object' ? (payload as HealthPayload) : null;
  } catch {
    return null;
  }
}

export function isSuzentOk(payload: HealthPayload | null): boolean {
  return payload?.app === 'suzent' && payload.status === 'ok';
}

function canonical(dir: string): string {
  try {
    return fs.realpathSync.native(dir);
  } catch {
    return path.resolve(dir);
  }
}

function samePath(a: string, b: string, platform: NodeJS.Platform): boolean {
  const left = canonical(a);
  const right = canonical(b);
  return platform === 'win32' ? left.toLowerCase() === right.toLowerCase() : left === right;
}

/**
 * Whether the backend that sent `payload` belongs to this install.
 *
 * A bundled app only shares a backend with another bundled install of the same
 * version (it reports no source root). A development run only shares one
 * started from the same checkout and version. Returns the reason otherwise.
 */
export function identityProblem(
  payload: HealthPayload | null,
  layout: Layout,
  appVersion: string,
  port: number,
  platform: NodeJS.Platform = process.platform
): string | null {
  const version = typeof payload?.version === 'string' ? payload.version : 'unknown';
  const root = typeof payload?.source_root === 'string' ? payload.source_root : null;
  const versionMatches = version === appVersion;
  if (layout.mode === 'bundled') {
    if (isSuzentOk(payload) && versionMatches && root === null) return null;
    return `Backend on port ${port} (version ${version}) is not this Suzent (version ${appVersion}). Stop the other installation or choose a different SUZENT_PORT; no process was stopped.`;
  }
  const expected = layout.sourceRoot;
  if (
    isSuzentOk(payload) &&
    versionMatches &&
    root !== null &&
    expected !== null &&
    samePath(root, expected, platform)
  ) {
    return null;
  }
  return `Backend on port ${port} belongs to ${root ?? 'unknown source'} (version ${version}), not this installation at ${expected ?? 'unknown'} (version ${appVersion}). Stop or reconfigure the other installation, or choose a different SUZENT_PORT; no process was stopped.`;
}

/** Whether a bundled app may even consider a backend: dev backends are never shared. */
export function mayAttach(payload: HealthPayload | null, layout: Layout): boolean {
  if (layout.mode !== 'bundled') return true;
  return payload?.source_root === undefined || payload.source_root === null;
}
