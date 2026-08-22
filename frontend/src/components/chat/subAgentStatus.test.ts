import { describe, expect, it } from 'vitest';

import { tForLocale } from '../../i18n';
import {
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

  it('passes an unknown status through rather than inventing a label', () => {
    expect(subAgentStatusLabel('warp-drive', t)).toBe('warp-drive');
  });
});
