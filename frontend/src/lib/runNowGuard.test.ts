import { describe, expect, it } from 'vitest';
import { canStartRun } from './runNowGuard';

describe('canStartRun', () => {
  it('allows one idle run and blocks a running or pending one', () => {
    expect(canStartRun(false, false)).toBe(true);
    expect(canStartRun(true, false)).toBe(false);
    expect(canStartRun(false, true)).toBe(false);
    expect(canStartRun(true, true)).toBe(false);
  });
});
