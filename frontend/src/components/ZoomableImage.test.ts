import { describe, expect, it } from 'vitest';
import { zoomImage } from './ZoomableImage';

describe('image zoom', () => {
  it('keeps the image point under the pointer stationary', () => {
    expect(zoomImage({ scale: 1, x: 0, y: 0 }, 2, 100, -50)).toEqual({ scale: 2, x: -100, y: 50 });
    expect(zoomImage({ scale: 2, x: -100, y: 50 }, 4, 100, -50)).toEqual({
      scale: 4,
      x: -300,
      y: 150,
    });
  });
  it('limits magnification and resets pan at fit size', () => {
    expect(zoomImage({ scale: 2, x: 90, y: -50 }, 0.5, 20, 10)).toEqual({ scale: 1, x: 0, y: 0 });
    expect(zoomImage({ scale: 1, x: 0, y: 0 }, 20, 0, 0).scale).toBe(8);
  });
});
