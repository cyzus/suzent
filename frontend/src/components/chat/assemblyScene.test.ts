import { describe, expect, it } from 'vitest';
import { assemblyFrame } from './assemblyScene';

describe('assembly scene', () => {
  it('scans only after the shell forms and before the eyes wake', () => {
    const scan = (seconds: number) =>
      assemblyFrame(seconds).filter((mark) =>
        ['#737980', '#c4c7ca', '#a8adb3', '#e0e2e4'].includes(mark.color)
      );
    expect(scan(0.2)).toHaveLength(0);
    const marks = scan(2.2 / 1.45);
    expect(marks.length).toBeGreaterThan(0);
    expect(marks.some((mark) => mark.width === 6)).toBe(true);
    expect(marks.some((mark) => mark.width === 1.2)).toBe(true);
    expect(scan(3.2 / 1.45)).toHaveLength(0);
  });

  it('moves only finished robots one slot at a time for reduced motion', () => {
    const shadows = (seconds: number) =>
      assemblyFrame(seconds, true).filter((mark) => mark.color === '#000');
    for (const seconds of [0, 1, 2.2, 2.5]) {
      const marks = assemblyFrame(seconds, true);
      expect(marks.filter((mark) => mark.color === '#e8eceb')).toHaveLength(
        shadows(seconds).length * 2
      );
      expect(marks.some((mark) => mark.width !== undefined)).toBe(false);
    }
    expect(assemblyFrame(1.7, true)).toEqual(assemblyFrame(0, true));
    expect(shadows(2.2).at(-1)!.points[0][0]).toBeGreaterThan(shadows(0).at(-1)!.points[0][0]);
    expect(assemblyFrame(2.6, true)).toEqual(assemblyFrame(0, true));
  });

  it('keeps geometry and opacity valid throughout multiple cycles', () => {
    for (let i = 0; i <= 400; i++) {
      const marks = assemblyFrame(i / 30);
      expect(marks.every((mark) => mark.alpha >= 0 && mark.alpha <= 1)).toBe(true);
      expect(
        marks.every((mark) => mark.points.every((point) => point.every(Number.isFinite)))
      ).toBe(true);
    }
  });
});
