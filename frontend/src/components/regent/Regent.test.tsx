import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { FocalAgentStatus } from '../../lib/focalAgent';
import { RegentIdentity } from './RegentHeader';
import { RegentCube } from './RegentCube';
import { RegentMark } from './RegentMark';
import { regentState } from './regentState';

vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number>) =>
      values?.count !== undefined ? `${key}:${values.count}` : key,
  }),
}));

const status = (extra: Partial<FocalAgentStatus> = {}): FocalAgentStatus => ({
  chatId: 'focal-suzent',
  title: 'Regent',
  waiting: 0,
  running: false,
  ...extra,
});
const text = (html: string): string =>
  html
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

describe('regentState', () => {
  it('is working while Regent runs, even with things waiting', () => {
    expect(regentState(status({ running: true, waiting: 2 }))).toBe('working');
    expect(regentState(status({ waiting: 2 }))).toBe('waiting');
    expect(regentState(status())).toBe('idle');
    expect(regentState(null)).toBe('idle');
  });
});

describe('Regent marks', () => {
  it('sizes the flat mark by its head, with the circlet rising above the slot', () => {
    const html = renderToStaticMarkup(<RegentMark size={24} state="waiting" />);
    expect(html).toContain('data-regent-state="waiting"');
    expect(html).toContain('width="24"');
    expect(html).toContain('margin-top:-9.6px');
    expect(html).toContain('regent-gem');
  });

  it('gives the cube the same state hooks and its circlet', () => {
    const html = renderToStaticMarkup(<RegentCube size={52} state="working" />);
    expect(html).toContain('data-regent-state="working"');
    expect(html.match(/regent-cube-band/g)).toHaveLength(32);
    expect(html).toContain('regent-cube-gem');
  });
});

describe('RegentIdentity', () => {
  it('reads as Suzent Regent in one row, with no pill when all is clear', () => {
    const html = renderToStaticMarkup(<RegentIdentity status={status()} state="idle" />);
    expect(text(html)).toBe('chatList.focal.brand chatList.focal.name');
    expect(html).not.toContain('regent-cube');
  });

  it('pills working first, then what waits on the user', () => {
    const pill = (value: FocalAgentStatus, state: 'idle' | 'working' | 'waiting'): string =>
      text(renderToStaticMarkup(<RegentIdentity status={value} state={state} />));
    expect(pill(status({ waiting: 1 }), 'working')).toContain('chatList.focal.working');
    expect(pill(status({ waiting: 1 }), 'waiting')).toContain('chatList.focal.waitingCount:1');
    expect(pill(status(), 'idle')).toBe('chatList.focal.brand chatList.focal.name');
  });
});
