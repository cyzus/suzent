import { describe, expect, it } from 'vitest';
import { float32ToInt16, int16ToFloat32, rms, StreamingLinearResampler } from './pcm';

describe('PCM helpers', () => {
  it('round trips and clips samples', () => {
    const encoded = float32ToInt16(Float32Array.from([-2, -0.5, 0, 0.5, 2]));
    expect(Array.from(encoded)).toEqual([-32768, -16384, 0, 16384, 32767]);
    const decoded = int16ToFloat32(encoded);
    expect(decoded[1]).toBeCloseTo(-0.5, 4);
    expect(decoded[3]).toBeCloseTo(0.5, 4);
  });

  it.each([
    [16000, 24000],
    [24000, 16000],
    [48000, 24000],
  ])('keeps continuity from %i to %i Hz', (inputRate, outputRate) => {
    const input = Float32Array.from({ length: inputRate / 10 }, (_, index) => index / inputRate);
    const split = Math.floor(input.length / 2);
    const resampler = new StreamingLinearResampler(inputRate, outputRate);
    const output = [
      ...resampler.process(input.slice(0, split)),
      ...resampler.process(input.slice(split)),
    ];
    expect(output.length).toBeCloseTo(outputRate / 10, -1);
    for (let index = 1; index < output.length; index += 1)
      expect(output[index]).toBeGreaterThan(output[index - 1]);
  });

  it.each([
    [16000, 24000],
    [48000, 24000],
  ])('matches single-chunk output when split into many chunks (%i -> %i)', (inRate, outRate) => {
    const input = Float32Array.from({ length: 1000 }, (_, i) => Math.sin(i / 7));
    const whole = new StreamingLinearResampler(inRate, outRate).process(input);
    const chunked = new StreamingLinearResampler(inRate, outRate);
    const parts: number[] = [];
    for (let start = 0; start < input.length; start += 37)
      parts.push(...chunked.process(input.slice(start, start + 37)));
    expect(parts.length).toBe(whole.length);
    for (let i = 0; i < whole.length; i += 1) expect(parts[i]).toBeCloseTo(whole[i], 5);
  });

  it('computes RMS', () => expect(rms(Float32Array.from([1, -1]))).toBe(1));
});
