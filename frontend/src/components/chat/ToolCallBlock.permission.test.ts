import { describe, expect, it } from 'vitest';
import type { ToolPermissionDecision } from '../../types/agui';
import { tForLocale } from '../../i18n';
import { shouldShowPolicyAllowedBadge } from './ToolCallBlock';

function decision(
  overrides: Partial<ToolPermissionDecision> = {},
): ToolPermissionDecision {
  return {
    toolCallId: 'call-1',
    toolName: 'run_command',
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

describe('permission confidence labels', () => {
  it('identifies confidence explicitly instead of showing a bare level', () => {
    expect(tForLocale(
      'en',
      'toolCallBlock.permissionConfidenceBadge',
      { value: tForLocale('en', 'toolCallBlock.permissionConfidenceLevels.high') },
    )).toBe('High confidence');
    expect(tForLocale(
      'zh-CN',
      'toolCallBlock.permissionConfidenceBadge',
      { value: tForLocale('zh-CN', 'toolCallBlock.permissionConfidenceLevels.high') },
    )).toBe('置信度：高');
  });
});
