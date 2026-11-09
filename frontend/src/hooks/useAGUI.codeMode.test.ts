import { expect, it } from 'vitest';
import { processEvent } from './useAGUI';
import type { AGUIPart } from '../types/agui';

it('links a call made from a code snippet to its run_code call', () => {
  let parts: AGUIPart[] = processEvent(
    { type: 'TOOL_CALL_START', data: { toolCallId: 'run-1', toolCallName: 'run_code' } },
    []
  ).parts;
  parts = processEvent(
    {
      type: 'CUSTOM',
      data: {
        name: 'code_mode_call',
        value: { toolCallId: 'run-1__1', parentToolCallId: 'run-1' },
      },
    },
    parts
  ).parts;
  parts = processEvent(
    { type: 'TOOL_CALL_START', data: { toolCallId: 'run-1__1', toolCallName: 'read_file' } },
    parts
  ).parts;
  parts = processEvent(
    { type: 'TOOL_CALL_RESULT', data: { toolCallId: 'run-1__1', content: 'hello' } },
    parts
  ).parts;

  const nested = parts.find((part) => part.toolCallId === 'run-1__1');
  expect(parts).toHaveLength(2);
  expect(nested?.toolName).toBe('read_file');
  expect(nested?.parentToolCallId).toBe('run-1');
  expect(nested?.state).toBe('completed');
  expect(nested?.output).toBe('hello');
});
