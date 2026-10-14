import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { processEvent } from '../../hooks/useAGUI';
import type { AGUIPart } from '../../types/agui';
import { ToolCallBlock } from './ToolCallBlock';
import { isFailedToolOutput, toolCallFailed } from './toolSummary';

const VALIDATION_RETRY =
  '2 validation errors:\n```json\n[{"type": "missing", "loc": ["content"], "msg": "Field required"}]\n```\n\nFix the errors and try again.';

function renderTool(props: Partial<React.ComponentProps<typeof ToolCallBlock>>): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ToolCallBlock toolName="run_command" {...props} />
    </I18nProvider>
  );
}

// Matches the stroke of the success checkmark and the failure cross.
const CHECK = 'M5 13l4 4L19 7';
const CROSS = 'M6 6l12 12M18 6L6 18';

describe('failed tool calls', () => {
  it('shows a failure, not a checkmark, when the backend reports the call failed', () => {
    const html = renderTool({ output: VALIDATION_RETRY, outcome: 'failed' });
    expect(html).toContain(CROSS);
    expect(html).not.toContain(CHECK);
  });

  it('shows a failure for a ToolResult that reports success: false', () => {
    const html = renderTool({
      output: JSON.stringify({ success: false, message: 'No such file', error_code: 'not_found' }),
    });
    expect(html).toContain(CROSS);
    expect(html).not.toContain(CHECK);
  });

  it('shows a failure for a failed outcome that left no output', () => {
    const html = renderTool({ outcome: 'interrupted' });
    expect(html).toContain(CROSS);
    expect(html).not.toContain(CHECK);
  });

  it('keeps the checkmark for an ordinary result', () => {
    const html = renderTool({ output: JSON.stringify({ success: true, message: 'ok' }) });
    expect(html).toContain(CHECK);
    expect(html).not.toContain(CROSS);
  });

  it('reads failures out of stored Python-repr envelopes', () => {
    expect(isFailedToolOutput("{'success': False, 'message': 'boom'}")).toBe(true);
    expect(isFailedToolOutput("{'success': True, 'message': 'ok'}")).toBe(false);
    expect(isFailedToolOutput('```json\n{"success": false}\n```')).toBe(true);
    expect(toolCallFailed('interrupted', 'whatever')).toBe(true);
    expect(toolCallFailed(undefined, 'plain text output')).toBe(false);
  });

  it('treats a command that exited non-zero as failed', () => {
    const exited = (code: number | null) =>
      JSON.stringify({ success: true, message: 'out', metadata: { returncode: code } });
    expect(isFailedToolOutput(exited(1))).toBe(true);
    expect(isFailedToolOutput(exited(0))).toBe(false);
    expect(isFailedToolOutput(exited(null))).toBe(false);
    expect(
      isFailedToolOutput(
        JSON.stringify({ success: true, message: 'done', metadata: { done: true, exit_code: 2 } })
      )
    ).toBe(true);
    expect(isFailedToolOutput("{'success': True, 'message': 'x', 'returncode': 127}")).toBe(true);
    expect(isFailedToolOutput("{'success': True, 'message': 'x', 'returncode': 0}")).toBe(false);
  });

  it('records the outcome the backend streams after the result', () => {
    let parts: AGUIPart[] = [];
    for (const data of [
      { type: 'TOOL_CALL_START', toolCallId: 'call-1', toolCallName: 'run_command' },
      { type: 'TOOL_CALL_RESULT', toolCallId: 'call-1', content: VALIDATION_RETRY },
      {
        type: 'CUSTOM',
        name: 'tool_call_outcome',
        value: { toolCallId: 'call-1', outcome: 'failed' },
      },
    ]) {
      parts = processEvent({ type: data.type, data }, parts).parts;
    }
    expect(parts).toHaveLength(1);
    expect(parts[0].outcome).toBe('failed');
    // Not a denial: that is what state 'error' means.
    expect(parts[0].state).toBe('completed');
  });
});
