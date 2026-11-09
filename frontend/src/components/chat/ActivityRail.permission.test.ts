import { describe, expect, it } from 'vitest';

import type { AGUIPart } from '../../types/agui';
import {
  getAguiActivityLabel,
  hasAguiUserResolution,
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
    expect(getAguiActivityLabel(chunks, false)).toBe('Approval needed: Run command');
  });

  it('does not keep an interrupted orphan tool call pending', () => {
    const part = toolPart();
    const chunks = [{ chunk: { type: 'tool', items: [part] } }];

    expect(isActionableAguiApproval(part)).toBe(false);
    expect(hasAguiPendingApproval(chunks)).toBe(false);
    expect(getAguiActivityLabel(chunks, false)).toBe('Run command');
  });
});

describe('hasAguiUserResolution', () => {
  const asked = {
    type: 'tool' as const,
    toolCallId: 'call-1',
    toolName: 'run_command',
    state: 'running' as const,
    permission: {
      behavior: 'ask' as const,
      reason: 'r',
      reasonCode: 'c',
      risk: 'high' as const,
      actions: [],
    },
  };

  it('holds the rail open once the user has decided on a call in it', () => {
    expect(hasAguiUserResolution([{ chunk: { type: 'tool', items: [asked] } }])).toBe(true);
  });

  it('leaves rails with only auto-decided calls alone', () => {
    const { permission: _omit, ...plain } = asked;
    void _omit;
    expect(hasAguiUserResolution([{ chunk: { type: 'tool', items: [plain] } }])).toBe(false);
  });
});
