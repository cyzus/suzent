import { describe, expect, it } from 'vitest';
import { focalRequestText } from './focalAgent';

describe('focalRequestText', () => {
  it('reads what SUZENT asked a session for', () => {
    const row =
      '[Agent message from SUZENT (focal-suzent)]\n<!-- suzent-agent-inbox:m1 -->\nBuild the **landing page**.\nUse the brand colours.';

    expect(focalRequestText(row)).toBe('Build the **landing page**.\nUse the brand colours.');
  });

  it('leaves other agents and triggers alone', () => {
    expect(
      focalRequestText('[Agent message from Ops (chat-9)]\n<!-- suzent-agent-inbox:m2 -->\nHi')
    ).toBeNull();
    expect(focalRequestText('**Scheduled task**\nRun the report')).toBeNull();
    expect(focalRequestText(undefined)).toBeNull();
  });

  it('ignores an empty request', () => {
    expect(
      focalRequestText('[Agent message from SUZENT (focal-suzent)]\n<!-- suzent-agent-inbox:m3 -->')
    ).toBeNull();
  });
});
