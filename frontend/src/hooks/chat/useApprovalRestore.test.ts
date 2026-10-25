import { describe, expect, it } from 'vitest';
import { permissionApprovalsToParts, resolvedApprovalToolCallIds } from './useApprovalRestore';
import type { AGUIPart } from '../../types/agui';

describe('restored approval resolution', () => {
  const resolved = (part: Partial<AGUIPart>): boolean =>
    resolvedApprovalToolCallIds([
      {
        role: 'assistant',
        content: '',
        parts: [{ type: 'tool', toolCallId: 'pending-call', ...part }],
      },
    ]).has('pending-call');

  it('keeps restored approvals when snapshots are running or incomplete', () => {
    expect(resolved({ state: 'running' })).toBe(false);
    expect(resolved({ state: 'running', output: 'partial shell output' })).toBe(false);
    expect(resolved({})).toBe(false);
    expect(resolved({ state: 'approval-requested', approvalId: 'approval' })).toBe(false);
  });

  it('clears restored approvals only on terminal evidence', () => {
    expect(resolved({ state: 'completed', output: '' })).toBe(true);
    expect(resolved({ state: 'error' })).toBe(true);
    expect(resolved({ output: 'legacy result' })).toBe(true);
  });
});

describe('permissionApprovalsToParts', () => {
  it('reconstructs an actionable approval from backend state', () => {
    const parts = permissionApprovalsToParts([
      {
        approvalId: 'approval-1',
        toolCallId: 'call-1',
        toolName: 'run_command',
        args: { content: 'npm test' },
        decision: {
          behavior: 'ask',
          reason: 'Needs approval',
          reasonCode: 'shell_policy_ask',
          risk: 'high',
          actions: [
            {
              id: 'allow_once',
              label: 'Allow',
              behavior: 'allow',
              scope: 'once',
            },
          ],
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
