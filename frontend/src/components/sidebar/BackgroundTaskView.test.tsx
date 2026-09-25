import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BackgroundTaskSummary } from '../../hooks/useBackgroundTasks';
import { BackgroundTaskView } from './BackgroundTaskView';

const state = vi.hoisted(() => ({ taskStates: {} as Record<string, BackgroundTaskSummary> }));
vi.mock('../../hooks/useBackgroundTasks', () => ({ useBackgroundTasks: () => state }));
vi.mock('../../i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      `${key}${params ? JSON.stringify(params) : ''}`,
  }),
}));
vi.mock('./SubAgentView', () => ({
  SubAgentView: ({ taskId }: { taskId: string }) => <div>agent-detail:{taskId}</div>,
}));

beforeEach(() => {
  state.taskStates = {};
});

describe('Background task details', () => {
  it('retains the agent detail panel for subagents', () => {
    expect(renderToStaticMarkup(<BackgroundTaskView taskId="sub_123" />)).toContain(
      'agent-detail:sub_123'
    );
  });

  it('shows command failure, exit code, and escaped output without agent controls', () => {
    state.taskStates.shell_abc = {
      task_id: 'shell_abc',
      command_id: 'abc',
      kind: 'shell',
      parent_chat_id: 'chat',
      chat_id: '',
      description: 'Build project',
      tools_allowed: [],
      status: 'failed',
      started_at: null,
      exit_code: 7,
      result_summary: '<script>bad</script>',
      error: 'Command failed',
    };
    const html = renderToStaticMarkup(<BackgroundTaskView taskId="shell_abc" />);
    expect(html).toContain('Build project');
    expect(html).toContain('backgroundTasks.exitCode');
    expect(html).toContain('&quot;code&quot;:7');
    expect(html).toContain('&lt;script&gt;bad&lt;/script&gt;');
    expect(html).toContain('Command failed');
    expect(html).not.toContain('subAgents.stop');
    expect(html).not.toContain('agent-detail:');
  });

  it('offers a stop action for a running command', () => {
    state.taskStates.shell_abc = {
      task_id: 'shell_abc',
      kind: 'shell',
      parent_chat_id: 'chat',
      chat_id: '',
      description: 'Serve',
      tools_allowed: [],
      status: 'running',
      started_at: null,
    };
    expect(renderToStaticMarkup(<BackgroundTaskView taskId="shell_abc" />)).toContain(
      'subAgents.stop'
    );
  });
});
