import { describe, expect, it } from 'vitest';

import { getBackendCompatibilityIssue } from './api';

const frontend = {
  version: '1.2.3',
  apiVersion: 1,
  buildCommit: 'abcdef123456',
};

describe('backend compatibility', () => {
  it('accepts an exact release identity match', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: 'abcdef123456',
    }, frontend)).toBeNull();
  });

  it('rejects API protocol mismatches', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 2,
      buildCommit: 'abcdef123456',
    }, frontend)).toEqual({ kind: 'api', frontend: '1', backend: '2' });
  });

  it('rejects different known build commits', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.3',
      apiVersion: 1,
      buildCommit: '999999999999',
    }, frontend)).toEqual({ kind: 'build', frontend: 'abcdef12', backend: '99999999' });
  });

  it('falls back to semantic versions when commits are unavailable', () => {
    expect(getBackendCompatibilityIssue({
      backendVersion: '1.2.2',
      apiVersion: 1,
      buildCommit: 'unknown',
    }, frontend)).toEqual({ kind: 'version', frontend: '1.2.3', backend: '1.2.2' });
  });
});
