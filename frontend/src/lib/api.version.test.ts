import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  BackendVersionTimeoutError,
  fetchSystemVersion,
  getBackendCompatibilityIssue,
} from './api';

const frontend = {
  version: '1.2.3',
  apiVersion: 1,
  buildCommit: 'abcdef123456',
  enforceBuildCommit: true,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('backend version request', () => {
  it('retries a transient abort during WebView refresh', async () => {
    vi.stubGlobal('window', { setTimeout, clearTimeout });
    const abortError = new Error('signal is aborted without reason');
    abortError.name = 'AbortError';
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(abortError)
      .mockResolvedValueOnce(new Response(JSON.stringify({
        backend_version: '1.2.3',
        api_version: 1,
        build_commit: 'abcdef123456',
        development_mode: false,
      }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchSystemVersion({ retryDelayMs: 0 })).resolves.toEqual({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: 'abcdef123456',
      developmentMode: false,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('returns a typed timeout after repeated aborts', async () => {
    vi.stubGlobal('window', { setTimeout, clearTimeout });
    const abortError = new Error('aborted');
    abortError.name = 'AbortError';
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError));

    await expect(fetchSystemVersion({ attempts: 2, retryDelayMs: 0 }))
      .rejects.toBeInstanceOf(BackendVersionTimeoutError);
  });
});

describe('backend compatibility', () => {
  it('accepts an exact release identity match', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: 'abcdef123456',
      developmentMode: false,
    }, frontend)).toBeNull();
  });

  it('rejects API protocol mismatches', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 2,
      buildCommit: 'abcdef123456',
      developmentMode: false,
    }, frontend)).toEqual({ kind: 'api', frontend: '1', backend: '2' });
  });

  it('rejects different known build commits', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: '999999999999',
      developmentMode: false,
    }, frontend)).toEqual({ kind: 'build', frontend: 'abcdef12', backend: '99999999' });
  });

  it('allows commit changes while the Vite development server is running', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: '999999999999',
      developmentMode: false,
    }, { ...frontend, enforceBuildCommit: false })).toBeNull();
  });

  it('allows commit changes for a backend launched with suzent serve', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: '999999999999',
      developmentMode: true,
    }, frontend)).toBeNull();
  });

  it('falls back to semantic versions when commits are unavailable', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.2',
      apiVersion: 1,
      buildCommit: 'unknown',
      developmentMode: false,
    }, frontend)).toEqual({ kind: 'version', frontend: '1.2.3', backend: '1.2.2' });
  });
});
