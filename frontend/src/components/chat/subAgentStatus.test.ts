import { describe, expect, it } from 'vitest';

import { tForLocale } from '../../i18n';
import {
  isStreamStateStale,
  isSubAgentActive,
  isSubAgentTerminal,
  subAgentOutcomeLabel,
  subAgentStatusLabel,
} from './subAgentStatus';

const t = (key: string, params?: Record<string, unknown>) => tForLocale('en', key, params);

describe('sub-agent status vocabulary', () => {
  it('treats a stop as finished, not as still working', () => {
    expect(isSubAgentTerminal('cancelled')).toBe(true);
    expect(isSubAgentActive('cancelled')).toBe(false);
    expect(isSubAgentActive('queued')).toBe(true);
    expect(isSubAgentActive('running')).toBe(true);
    expect(isSubAgentTerminal('running')).toBe(false);
  });

  it('names each state in plain words', () => {
    expect(subAgentStatusLabel('running', t)).toBe('Running');
    expect(subAgentStatusLabel('completed', t)).toBe('Done');
    expect(subAgentStatusLabel('failed', t)).toBe('Failed');
    expect(subAgentStatusLabel('cancelled', t)).toBe('Stopped');
  });

  it('does not call a deliberate stop an error', () => {
    expect(subAgentOutcomeLabel('completed', t)).toBe('Result');
    expect(subAgentOutcomeLabel('failed', t)).toBe('Error');
    expect(subAgentOutcomeLabel('cancelled', t)).toBe('Stopped');
  });

  it('lets a finished answer outrank a stream that stopped mid-run', () => {
    // The EventSource dropped while the task was running; the poll that
    // followed is the only thing that knows it has since finished.
    expect(isStreamStateStale('running', 'completed')).toBe(true);
    expect(isStreamStateStale(undefined, 'failed')).toBe(true);
    // A live stream still ahead of the fetch keeps its say.
    expect(isStreamStateStale('completed', 'running')).toBe(false);
    expect(isStreamStateStale('running', 'running')).toBe(false);
    expect(isStreamStateStale('running', undefined)).toBe(false);
  });

  it('passes an unknown status through rather than inventing a label', () => {
    expect(subAgentStatusLabel('warp-drive', t)).toBe('warp-drive');
  });
});
