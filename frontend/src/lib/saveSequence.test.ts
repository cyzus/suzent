import { describe, expect, it } from 'vitest';
import { SaveSequence } from './saveSequence';

describe('SaveSequence', () => {
  it('keeps the newer result when an older save lands last', () => {
    const saves = new SaveSequence<string>();
    const enable = saves.begin();
    const disable = saves.begin();
    expect(saves.land(disable, 'off')).toBe('off');
    expect(saves.land(enable, 'on')).toBe('off');
    expect(saves.latest()).toBe('off');
  });

  it('knows when a newer save has started', () => {
    const saves = new SaveSequence<string>();
    const first = saves.begin();
    expect(saves.isNewest(first)).toBe(true);
    saves.begin();
    expect(saves.isNewest(first)).toBe(false);
  });
});
