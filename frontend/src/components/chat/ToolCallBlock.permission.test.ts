import { describe, expect, it } from 'vitest';
import type { ToolPermissionDecision } from '../../types/agui';
import { shouldShowPolicyAllowedBadge } from './ToolCallBlock';

function decision(
  overrides: Partial<ToolPermissionDecision> = {},
): ToolPermissionDecision {
  return {
    toolCallId: 'call-1',
    toolName: 'bash_execute',
    behavior: 'allow',
    source: 'policy',
    reason: 'Allowed by deterministic shell policy',
    reasonCode: 'shell_policy_allow',
    risk: 'safe',
    riskCategories: [],
    ...overrides,
  };
}

describe('policy permission badge', () => {
  it('shows state-changing deterministic policy allows', () => {
    expect(shouldShowPolicyAllowedBadge(decision())).toBe(true);
  });

  it('suppresses routine read-only policy allows', () => {
    expect(shouldShowPolicyAllowedBadge(decision({
      reasonCode: 'readonly_operation',
    }))).toBe(false);
  });
});
