import { describe, expect, it } from 'vitest';
import {
  capturePrependScrollSnapshot,
  restorePrependScrollSnapshot,
  type PrependScrollSnapshot,
} from './chatScrollAnchor';

function row(index: number, top: number, bottom: number): HTMLElement {
  return {
    dataset: { messageIndex: String(index) },
    getBoundingClientRect: () => ({ top, bottom }),
  } as unknown as HTMLElement;
}

function scroller({
  top = 100,
  scrollTop = 500,
  scrollHeight = 2_000,
  rows = [],
}: {
  top?: number;
  scrollTop?: number;
  scrollHeight?: number;
  rows?: HTMLElement[];
}): HTMLDivElement {
  return {
    scrollTop,
    scrollHeight,
    getBoundingClientRect: () => ({ top }),
    querySelectorAll: () => rows,
    querySelector: (selector: string) => {
      const index = selector.match(/"(\d+)"/)?.[1];
      return rows.find((item) => item.dataset.messageIndex === index) ?? null;
    },
  } as unknown as HTMLDivElement;
}

describe('prepend scroll anchoring', () => {
  it('captures the first row that is visible in the viewport', () => {
    const el = scroller({ rows: [row(10, 20, 90), row(11, 90, 180), row(12, 180, 260)] });

    expect(capturePrependScrollSnapshot(el)).toEqual({
      scrollHeight: 2_000,
      scrollTop: 500,
      anchorMessageIndex: 11,
      anchorViewportOffset: -10,
    });
  });

  it('keeps the same visible row at the same viewport offset after a prepend', () => {
    const el = scroller({ scrollTop: 500, rows: [row(11, 390, 480)] });
    const snapshot: PrependScrollSnapshot = {
      scrollHeight: 2_000,
      scrollTop: 500,
      anchorMessageIndex: 11,
      anchorViewportOffset: -10,
    };

    restorePrependScrollSnapshot(el, snapshot);

    expect(el.scrollTop).toBe(800);
  });

  it('does not double-adjust when native scroll anchoring already preserved the row', () => {
    const el = scroller({ scrollTop: 800, rows: [row(11, 90, 180)] });
    const snapshot: PrependScrollSnapshot = {
      scrollHeight: 2_000,
      scrollTop: 500,
      anchorMessageIndex: 11,
      anchorViewportOffset: -10,
    };

    restorePrependScrollSnapshot(el, snapshot);

    expect(el.scrollTop).toBe(800);
  });

  it('falls back to the scroll-height delta if the anchor is unavailable', () => {
    const el = scroller({ scrollTop: 500, scrollHeight: 2_600 });
    const snapshot: PrependScrollSnapshot = {
      scrollHeight: 2_000,
      scrollTop: 500,
      anchorMessageIndex: 11,
      anchorViewportOffset: -10,
    };

    restorePrependScrollSnapshot(el, snapshot);

    expect(el.scrollTop).toBe(1_100);
  });
});
