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

  it('holds a fixed assembled scene for reduced motion', () => {
    expect(assemblyFrame(0, true)).toEqual(assemblyFrame(100, true));
    expect(assemblyFrame(0, true).some((mark) => mark.color === '#e8eceb')).toBe(true);
  });

  it('keeps geometry and opacity valid throughout multiple cycles', () => {
    for (let i = 0; i <= 400; i++) {
      for (const mark of assemblyFrame(i / 30)) {
        expect(mark.alpha).toBeGreaterThanOrEqual(0);
        expect(mark.alpha).toBeLessThanOrEqual(1);
        for (const point of mark.points) expect(point.every(Number.isFinite)).toBe(true);
      }
    }
  });
});
