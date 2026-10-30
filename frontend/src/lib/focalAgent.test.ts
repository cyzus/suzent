import { afterEach, describe, expect, it, vi } from 'vitest';
import { focalRequestText, readFocalBoardOpen, writeFocalBoardOpen } from './focalAgent';

describe('focalRequestText', () => {
  it('reads what Regent asked a session for', () => {
    const row =
      '[Agent message from Regent (focal-suzent)]\n<!-- suzent-agent-inbox:m1 -->\nBuild the **landing page**.\nUse the brand colours.';

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
      focalRequestText('[Agent message from Regent (focal-suzent)]\n<!-- suzent-agent-inbox:m3 -->')
    ).toBeNull();
  });
});

describe('Regent board default', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('stays closed until the user opens it on Regent', () => {
    const store = new Map<string, string>();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => store.set(key, value),
      },
    });
    // What the old auto-opening board left behind must not reopen it.
    store.set('suzent.focal.boardOpen', 'true');
    expect(readFocalBoardOpen()).toBe(false);
    writeFocalBoardOpen(true);
    expect(readFocalBoardOpen()).toBe(true);
    writeFocalBoardOpen(false);
    expect(readFocalBoardOpen()).toBe(false);
  });
});
