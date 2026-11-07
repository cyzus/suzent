import { describe, expect, it } from 'vitest';
import { fileContextExtras } from './fileContextActions';

describe('fileContextExtras', () => {
  it('offers download only for a file in the browser', () => {
    expect(fileContextExtras({ isDirectory: false, web: true, canMutate: true })).toEqual({
      download: true,
      upload: false,
    });
    expect(fileContextExtras({ isDirectory: false, web: false, canMutate: true })).toEqual({
      download: false,
      upload: false,
    });
  });

  it('offers upload into a writable folder and never a download of the folder', () => {
    expect(fileContextExtras({ isDirectory: true, web: true, canMutate: true })).toEqual({
      download: false,
      upload: true,
    });
    expect(fileContextExtras({ isDirectory: true, web: true, canMutate: false })).toEqual({
      download: false,
      upload: false,
    });
  });

  it('still lets the browser save a file that lives under mounts', () => {
    expect(fileContextExtras({ isDirectory: false, web: true, canMutate: false })).toEqual({
      download: true,
      upload: false,
    });
  });
});
