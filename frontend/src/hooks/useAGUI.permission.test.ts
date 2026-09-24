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
      [] as AGUIPart[]
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
      decisionResult.parts
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
      [] as AGUIPart[]
    );

    expect(result.parts).toHaveLength(1);
    expect(result.parts[0].state).toBe('approval-requested');
    expect(result.parts[0].permission?.actions).toEqual(decision.actions);
    expect(result.parts[0].permission?.actions[1].feedbackKind).toBe('reject');
  });
});

it('restores resolved ACP approvals without resurrecting the action buttons', () => {
  const request = { requestId: 'request', options: [], toolCall: {} };
  const pending = processEvent(
    { type: 'CUSTOM', data: { name: 'acp.permission_request', value: request } },
    []
  ).parts;
  const resolved = processEvent(
    {
      type: 'CUSTOM',
      data: { name: 'acp.permission_request', value: { ...request, resolved: 'approved' } },
    },
    pending
  ).parts;
  expect(resolved).toHaveLength(1);
  expect(resolved[0].acpPermission?.resolved).toBe('approved');
});

it('does not restore an already answered inline form from a snapshot', () => {
  const open = processEvent(
    {
      type: 'CUSTOM',
      data: { name: 'a2ui.render', value: { id: 'form', target: 'inline', deferred: true } },
    },
    []
  ).parts;
  const resolved = processEvent(
    { type: 'CUSTOM', data: { name: 'a2ui.resolved', value: { surfaceId: 'form' } } },
    open
  ).parts;
  expect(resolved).toEqual([]);
});

it('restores an unanswered inline form from a snapshot, still routed to /answer', () => {
  // Reloading mid-question replays the run from seq 0, so the pending surface
  // comes back through this same reducer. onMarkDeferred has to fire again:
  // it is what keeps the answer going to /canvas/{chat}/answer instead of
  // opening a new turn through /canvas/{chat}/action.
  const deferred: string[] = [];
  const restored = processEvent(
    {
      type: 'CUSTOM',
      data: { name: 'a2ui.render', value: { id: 'form', target: 'inline', deferred: true } },
    },
    [],
    undefined,
    (surfaceId) => deferred.push(surfaceId)
  ).parts;

  expect(restored).toHaveLength(1);
  expect(restored[0].surface?.id).toBe('form');
  expect(deferred).toEqual(['form']);
});

it.each([
  { type: 'TOOL_CALL_START', data: { toolCallId: 'call-1', toolCallName: 'BashTool' } },
  {
    type: 'CUSTOM',
    data: {
      name: 'tool_approval_request',
      value: { toolCallId: 'call-1', toolName: 'BashTool', approvalId: 'approval-1' },
    },
  },
  {
    type: 'CUSTOM',
    data: {
      name: 'tool_approval_result',
      value: { toolCallId: 'call-1', toolName: 'BashTool', status: 'executed', output: 'ok' },
    },
  },
  {
    type: 'CUSTOM',
    data: {
      name: 'tool_permission_resolution',
      value: { toolCallId: 'call-1', toolName: 'BashTool', behavior: 'allow' },
    },
  },
])('restores the tool name after a resolution created a placeholder: $type $data.name', (event) => {
  const seed = processEvent(
    {
      type: 'CUSTOM',
      data: {
        name: 'tool_permission_resolution',
        value: { toolCallId: 'call-1', behavior: 'allow' },
      },
    },
    []
  ).parts;
  const result = processEvent(event, seed).parts;
  expect(result).toHaveLength(1);
  expect(result[0].toolName).toBe('BashTool');
  expect(result[0].permissionResolution?.behavior).toBe('allow');
});

it('shows the resolved tool name immediately without an earlier tool start', () => {
  const result = processEvent(
    {
      type: 'CUSTOM',
      data: {
        name: 'tool_permission_resolution',
        value: { toolCallId: 'call-1', toolName: 'BashTool', behavior: 'allow' },
      },
    },
    []
  ).parts;
  expect(result[0].toolName).toBe('BashTool');
  expect(result[0].state).toBe('running');
});
