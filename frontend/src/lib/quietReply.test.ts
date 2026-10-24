import { describe, expect, it } from 'vitest';
import { isQuietReply } from './quietReply';

describe('isQuietReply', () => {
  it('recognises the bare token and a short aside', () => {
    expect(isQuietReply('HEARTBEAT_OK')).toBe(true);
    expect(isQuietReply('  HEARTBEAT_OK\n')).toBe(true);
    expect(isQuietReply('All sessions on track. HEARTBEAT_OK')).toBe(true);
  });

  it('treats a report as a report', () => {
    expect(isQuietReply('')).toBe(false);
    expect(isQuietReply('The deploy needs your approval.')).toBe(false);
    expect(isQuietReply(`HEARTBEAT_OK ${'x'.repeat(301)}`)).toBe(false);
  });
});
