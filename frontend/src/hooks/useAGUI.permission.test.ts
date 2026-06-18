import { describe, expect, it } from 'vitest';
import { processEvent } from './useAGUI';
import type { AGUIPart } from '../types/agui';

describe('permission approval events', () => {
  it('preserves exactly the backend-provided actions and feedback declaration', () => {
    const decision = {
      behavior: 'ask',
      reason: 'Command requires approval',
      reasonCode: 'shell_policy_ask',
      risk: 'high',
      actions: [
        {
          id: 'allow_once',
          label: 'Allow',
          behavior: 'allow',
          scope: 'once',
        },
        {
          id: 'reject',
          label: 'Reject',
          behavior: 'deny',
          scope: 'once',
          feedbackKind: 'reject',
        },
      ],
    };
    const result = processEvent(
      {
        type: 'CUSTOM',
        data: {
          type: 'CUSTOM',
          name: 'tool_approval_request',
          value: {
            approvalId: 'call-1',
            toolCallId: 'call-1',
            toolName: 'bash_execute',
            args: { content: 'npm test' },
            decision,
          },
        },
      },
      [] as AGUIPart[],
    );

    expect(result.parts).toHaveLength(1);
    expect(result.parts[0].state).toBe('approval-requested');
    expect(result.parts[0].permission?.actions).toEqual(decision.actions);
    expect(result.parts[0].permission?.actions[1].feedbackKind).toBe('reject');
  });
});
