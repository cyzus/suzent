import { describe, expect, it } from 'vitest';

import { normalizePermissionMode } from './api';

describe('normalizePermissionMode', () => {
  it.each(['accept_edits', 'plan', 'strict_readonly', undefined])(
    'maps removed mode %s to default',
    value => {
      expect(normalizePermissionMode(value)).toBe('default');
    },
  );

  it.each(['default', 'auto', 'full_access'] as const)(
    'preserves public mode %s',
    value => {
      expect(normalizePermissionMode(value)).toBe(value);
    },
  );
});
