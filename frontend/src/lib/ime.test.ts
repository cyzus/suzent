import { describe, expect, it } from 'vitest';
import type React from 'react';
import { isImeComposing } from './ime';

function keydown(fields: { key: string; isComposing?: boolean; keyCode?: number }): KeyboardEvent {
  return { isComposing: false, keyCode: 0, ...fields } as unknown as KeyboardEvent;
}

describe('isImeComposing', () => {
  it('treats a keystroke during composition as the IME’s', () => {
    expect(isImeComposing(keydown({ key: 'Enter', isComposing: true }))).toBe(true);
  });

  it('catches the WebKit Enter that commits after compositionend', () => {
    expect(isImeComposing(keydown({ key: 'Enter', isComposing: false, keyCode: 229 }))).toBe(true);
  });

  it('lets a plain Enter through', () => {
    expect(isImeComposing(keydown({ key: 'Enter', keyCode: 13 }))).toBe(false);
  });

  it('reads the native event behind a React keyboard event', () => {
    const synthetic = {
      nativeEvent: keydown({ key: 'Escape', keyCode: 229 }),
    } as unknown as React.KeyboardEvent;
    expect(isImeComposing(synthetic)).toBe(true);
  });
});
