import { describe, expect, it } from 'vitest';
import { processEvent } from './useAGUI';
import type { AGUIPart } from '../types/agui';

describe('permission approval events', () => {
  it('retains the initial automatic decision and later user resolution', () => {
    const decisionResult = processEvent(
      {
        type: 'CUSTOM',
        data: {
          type: 'CUSTOM',
          name: 'tool_permission_decision',
          value: {
            toolCallId: 'call-1',
            toolName: 'run_command',
            behavior: 'ask',
            source: 'auto_classifier',
            reason: 'Command changes project files',
            reasonCode: 'auto_classifier_high_risk',
            risk: 'high',
            confidence: 'high',
            riskCategories: ['filesystem_write'],
            reviewerModel: 'review-model',
          },
        },
      },
      [] as AGUIPart[],
    );
    const resolutionResult = processEvent(
      {
        type: 'CUSTOM',
        data: {
          type: 'CUSTOM',
          name: 'tool_permission_resolution',
          value: {
            toolCallId: 'call-1',
            behavior: 'allow',
            source: 'user',
            actionId: 'allow_once',
            scope: 'once',
          },
        },
      },
      decisionResult.parts,
    );

    expect(resolutionResult.parts[0].permissionDecision?.source).toBe('auto_classifier');
    expect(resolutionResult.parts[0].permissionDecision?.confidence).toBe('high');
    expect(resolutionResult.parts[0].permissionResolution).toEqual({
      toolCallId: 'call-1',
      behavior: 'allow',
      source: 'user',
      actionId: 'allow_once',
      scope: 'once',
    });
  });

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
            toolName: 'run_command',
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
