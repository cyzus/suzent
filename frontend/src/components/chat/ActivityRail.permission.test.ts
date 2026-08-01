import { describe, expect, it } from 'vitest';

import type { AGUIPart } from '../../types/agui';
import {
  getAguiActivityLabel,
  hasAguiPendingApproval,
  isActionableAguiApproval,
} from './ActivityRail';

function toolPart(overrides: Partial<AGUIPart> = {}): AGUIPart {
  return {
    type: 'tool',
    toolCallId: 'call-1',
    toolName: 'run_command',
    state: 'approval-requested',
    ...overrides,
  };
}

describe('permission activity state', () => {
  it('shows approval needed only for a request with an actionable approval id', () => {
    const part = toolPart({ approvalId: 'approval-1' });
    const chunks = [{ chunk: { type: 'tool', items: [part] } }];

    expect(isActionableAguiApproval(part)).toBe(true);
    expect(hasAguiPendingApproval(chunks)).toBe(true);
    expect(getAguiActivityLabel(chunks, false)).toBe('Approval needed: run command');
  });

  it('does not keep an interrupted orphan tool call pending', () => {
    const part = toolPart();
    const chunks = [{ chunk: { type: 'tool', items: [part] } }];

    expect(isActionableAguiApproval(part)).toBe(false);
    expect(hasAguiPendingApproval(chunks)).toBe(false);
    expect(getAguiActivityLabel(chunks, false)).toBe('Using run command');
  });
});
