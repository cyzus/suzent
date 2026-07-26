import { describe, expect, it } from 'vitest';
import { getPendingApprovals } from './PermissionApprovalDock';

describe('getPendingApprovals', () => {
  it('returns only actionable approval parts', () => {
    const result = getPendingApprovals([
      {
        type: 'tool',
        toolCallId: 'call-1',
        toolName: 'bash_execute',
        args: JSON.stringify({ content: 'npm test' }),
        state: 'approval-requested',
        approvalId: 'approval-1',
        permission: {
          behavior: 'ask',
          reason: 'Needs approval',
          reasonCode: 'test',
          risk: 'medium',
          actions: [
            {
              id: 'allow_once',
              label: 'Allow',
              behavior: 'allow',
              scope: 'once',
            },
          ],
        },
        permissionDecision: {
          toolCallId: 'call-1',
          toolName: 'bash_execute',
          behavior: 'ask',
          source: 'auto_classifier',
          reason: 'Needs approval',
          reasonCode: 'test',
          risk: 'medium',
          confidence: 'high',
          riskCategories: ['command_execution'],
          reviewerModel: 'review-model',
        },
      },
      {
        type: 'tool',
        toolCallId: 'call-2',
        toolName: 'bash_execute',
        state: 'running',
      },
    ]);

    expect(result).toHaveLength(1);
    expect(result[0].approvalId).toBe('approval-1');
    expect(result[0].args.content).toBe('npm test');
    expect(result[0].source).toBe('auto_classifier');
    expect(result[0].confidence).toBe('high');
    expect(result[0].riskCategories).toEqual(['command_execution']);
  });
});
