import { describe, expect, it } from 'vitest';
import { permissionApprovalsToParts } from './useApprovalRestore';

describe('permissionApprovalsToParts', () => {
  it('reconstructs an actionable approval from backend state', () => {
    const parts = permissionApprovalsToParts([
      {
        approvalId: 'approval-1',
        toolCallId: 'call-1',
        toolName: 'bash_execute',
        args: { content: 'npm test' },
        decision: {
          behavior: 'ask',
          reason: 'Needs approval',
          reasonCode: 'shell_policy_ask',
          risk: 'high',
          actions: [{
            id: 'allow_once',
            label: 'Allow',
            behavior: 'allow',
            scope: 'once',
          }],
        },
      },
    ]);

    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({
      toolCallId: 'call-1',
      approvalId: 'approval-1',
      state: 'approval-requested',
    });
    expect(JSON.parse(parts[0].args || '{}').content).toBe('npm test');
  });
});
