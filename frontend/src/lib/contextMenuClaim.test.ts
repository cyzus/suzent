import { describe, expect, it } from 'vitest';
import {
  isNativeLinkTarget,
  isNativeMediaTarget,
  prefersNativeContextMenu,
} from './contextMenuClaim';

function element(match: string | null): EventTarget {
  return {
    closest: (selector: string) => (match !== null && selector.includes(match) ? {} : null),
  } as unknown as EventTarget;
}

const selection = {
  isCollapsed: false,
  toString: () => 'selected words',
  containsNode: () => true,
};

describe('prefersNativeContextMenu', () => {
  it('keeps links, fields, and a mouse right-click inside a selection', () => {
    expect(prefersNativeContextMenu(element('a[href]'), null, { button: 0 })).toBe(true);
    expect(prefersNativeContextMenu(element('textarea'), null, { button: 2 })).toBe(true);
    expect(prefersNativeContextMenu(element(null), selection, { button: 2 })).toBe(true);
    expect(isNativeLinkTarget(element('a[href]'))).toBe(true);
  });

  it('keeps a touch long-press for the app menu even if a word was highlighted', () => {
    expect(
      prefersNativeContextMenu(element(null), selection, { button: 0, pointerType: 'touch' })
    ).toBe(false);
    expect(
      prefersNativeContextMenu(element(null), selection, { button: 2, pointerType: 'touch' })
    ).toBe(false);
  });

  it('preserves native media actions instead of claiming the message menu', () => {
    for (const tag of ['img', 'video', 'audio']) {
      expect(prefersNativeContextMenu(element(tag), null, { button: 2 })).toBe(true);
      expect(isNativeMediaTarget(element(tag))).toBe(true);
    }
    expect(isNativeMediaTarget(element(null))).toBe(false);
  });

  it('claims an ordinary right-click with no selection', () => {
    expect(
      prefersNativeContextMenu(
        element(null),
        { isCollapsed: true, toString: () => '' },
        { button: 2 }
      )
    ).toBe(false);
    expect(isNativeLinkTarget(element(null))).toBe(false);
  });
});
