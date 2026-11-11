import { describe, expect, it } from 'vitest';
import { isBinaryServedFile, isVideoFile } from './fileUtils';

describe('isVideoFile', () => {
  it('recognises playable video extensions in any case', () => {
    expect(isVideoFile('clip.mp4')).toBe(true);
    expect(isVideoFile('Clip.MOV')).toBe(true);
    expect(isVideoFile('screen.webm')).toBe(true);
    expect(isVideoFile('notes.txt')).toBe(false);
  });

  it('serves videos directly instead of reading them as text', () => {
    expect(isBinaryServedFile('clip.mp4')).toBe(true);
  });
});
