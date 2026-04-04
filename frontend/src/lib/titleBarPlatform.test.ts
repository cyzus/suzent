import { describe, expect, it } from 'vitest';
import { detectDesktopPlatform } from './titleBarPlatform';

describe('detectDesktopPlatform', () => {
  it('detects macOS from navigator platform', () => {
    expect(detectDesktopPlatform('Mozilla/5.0', 'MacIntel')).toBe('macos');
  });

  it('detects Windows from user agent', () => {
    expect(detectDesktopPlatform('Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '')).toBe('windows');
  });

  it('detects Linux from platform', () => {
    expect(detectDesktopPlatform('Mozilla/5.0', 'Linux x86_64')).toBe('linux');
  });

  it('returns unknown when no known platform token exists', () => {
    expect(detectDesktopPlatform('Mozilla/5.0', 'Unknown')).toBe('unknown');
  });
});