import { describe, expect, it } from 'vitest';

import { tForLocale } from '../../i18n';
import {
  getRepeatedToolLabel,
  getToolSummary,
  isFailedToolOutput,
  normalizeToolName,
} from './toolSummary';

const t = (key: string, params?: Record<string, unknown>) => tForLocale('en', key, params);
const summarize = (toolName: string, args: Record<string, unknown> | null) =>
  getToolSummary(toolName, args, t);
const line = (toolName: string, args: Record<string, unknown> | null) => {
  const summary = summarize(toolName, args);
  return summary.detail ? `${summary.verb} ${summary.detail}` : summary.verb;
};

describe('getToolSummary', () => {
  it('summarizes file tools by basename', () => {
    expect(line('read_file', { file_path: '/repo/src/app/ToolCallBlock.tsx' })).toBe(
      'Read ToolCallBlock.tsx'
    );
    expect(line('write_file', { file_path: 'D:\\workspace\\suzent\\notes.md', content: 'x' })).toBe(
      'Write notes.md'
    );
    expect(line('edit_file', { file_path: 'src/main.py', old_string: 'a', new_string: 'b' })).toBe(
      'Edit main.py'
    );
  });

  it('includes the read offset when the model reads a slice', () => {
    expect(line('read_file', { file_path: 'src/main.py', offset: 120 })).toBe('Read main.py:120');
    expect(line('read_file', { file_path: 'src/main.py', offset: 0 })).toBe('Read main.py');
  });

  it('avoids tool jargon for the search tools', () => {
    expect(line('grep_search', { pattern: 'getToolSummary', include: '*.tsx' })).toBe(
      'Search code “getToolSummary” in *.tsx'
    );
    expect(line('grep_search', { pattern: 'getToolSummary' })).toBe('Search code “getToolSummary”');
    expect(line('glob_search', { pattern: '**/*.test.ts' })).toBe('Find files **/*.test.ts');
    expect(line('web_search', { query: 'tauri window transparency' })).toBe(
      'Search web “tauri window transparency”'
    );
    expect(line('webpage_fetch', { url: 'https://www.example.com/docs/page?ref=1' })).toBe(
      'Open page example.com/docs/page'
    );
  });

  it('promotes the model-written description to the headline for shell calls', () => {
    expect(line('run_command', { content: 'npm run build', description: 'Build the app' })).toBe(
      'Build the app'
    );
    expect(line('run_command', { content: 'npm run build' })).toBe('Run npm run build');
    expect(line('start_command', { content: 'npm run dev' })).toBe('Start npm run dev');
  });

  it('keeps a described shell command in the tooltip, not the row', () => {
    const summary = summarize('run_command', {
      content: "ssh host 'echo one; echo two'",
      description: 'Inspect the host',
    });
    expect(summary.detail).toBeNull();
    expect(summary.title).toBe("Inspect the host — ssh host 'echo one; echo two'");
  });

  it('marks multi-line shell commands as truncated', () => {
    expect(line('run_command', { content: 'cd frontend\nnpm run build' })).toBe(
      'Run cd frontend …'
    );
  });

  it('leads with the job a sub-agent was given, not the tool name', () => {
    expect(line('agent', { description: 'Audit the diff', subagent_type: 'Explore' })).toBe(
      'Audit the diff Explore agent'
    );
    expect(line('agent', { subagent_type: 'Explore' })).toBe('Delegate Explore agent');
    expect(line('agent', {})).toBe('Delegate sub-agent');
  });

  it('reads structured arguments for task tools', () => {
    expect(
      line('create_tasks', { tasks: [{ title: 'Wire up pills' }, { title: 'Add tests' }] })
    ).toBe('Add 2 tasks Wire up pills');
    expect(line('update_task', { task_id: 'T-3', status: 'completed' })).toBe(
      'Update task T-3 → completed'
    );
  });

  it('truncates long details but keeps the full text for the tooltip', () => {
    const query = 'a'.repeat(200);
    const summary = summarize('web_search', { query });
    expect(summary.detail).toHaveLength(64);
    expect(summary.detail?.endsWith('…')).toBe(true);
    expect(summary.title).toContain(query);
  });

  it('truncates an over-long description so it stays a headline', () => {
    const summary = summarize('run_command', { description: 'B'.repeat(120), content: 'ls' });
    expect(summary.verb).toHaveLength(44);
    expect(summary.detail).toBeNull();
  });

  it('collapses whitespace so a pill stays on one line', () => {
    expect(line('web_search', { query: 'tauri\n  window   transparency' })).toBe(
      'Search web “tauri window transparency”'
    );
  });

  it('falls back to the verb alone when args have not streamed in yet', () => {
    expect(line('web_search', null)).toBe('Search web');
    expect(summarize('read_file', {}).detail).toBeNull();
  });

  it('handles ACP and MCP tool names', () => {
    expect(line('Read', { file_path: 'src/main.py' })).toBe('Read main.py');
    expect(line('Bash', { command: 'ls', description: 'List files' })).toBe('List files');
    expect(line('mcp__github__create_issue', { title: 'Broken pill' })).toBe(
      'Call create issue Broken pill'
    );
  });

  it('falls back to a humanized name plus a headline argument for unknown tools', () => {
    expect(line('some_new_tool', { query: 'what happened' })).toBe(
      'Call some new tool what happened'
    );
    expect(line('some_new_tool', { irrelevant: 1 })).toBe('Call some new tool');
  });
});

describe('tense', () => {
  it('proposes, narrates, then reports the same call', () => {
    expect(getToolSummary('run_command', { content: 'npm test' }, t, 'imperative').verb).toBe(
      'Run'
    );
    expect(getToolSummary('run_command', { content: 'npm test' }, t, 'active').verb).toBe(
      'Running'
    );
    expect(getToolSummary('run_command', { content: 'npm test' }, t, 'past').verb).toBe('Ran');
    expect(getToolSummary('web_search', { query: 'x' }, t, 'active').verb).toBe('Searching web');
    expect(getToolSummary('web_search', { query: 'x' }, t, 'past').verb).toBe('Searched web');
  });

  it('defaults to the proposal form so an unknown state never claims a call ran', () => {
    expect(getToolSummary('read_file', { file_path: 'a.ts' }, t).verb).toBe('Read');
  });

  it('frames every tool it does not enumerate, whatever its name looks like', () => {
    expect(getToolSummary('create_issue', {}, t, 'imperative').verb).toBe('Call create issue');
    expect(getToolSummary('create_issue', {}, t, 'active').verb).toBe('Calling create issue');
    expect(getToolSummary('mcp__linear__send_reminder', {}, t, 'past').verb).toBe(
      'Called send reminder'
    );
    // A name that is not a verb phrase is carried, never conjugated.
    expect(getToolSummary('file_search', {}, t, 'past').verb).toBe('Called file search');
    expect(getToolSummary('weather_today', {}, t, 'active').verb).toBe('Calling weather today');
  });

  it('says a call failed instead of claiming it happened', () => {
    expect(getToolSummary('run_command', { content: 'npm test' }, t, 'failed').verb).toBe(
      'Failed to run'
    );
    expect(getToolSummary('web_search', { query: 'x' }, t, 'failed').verb).toBe(
      'Failed to search web'
    );
    expect(getToolSummary('mcp__linear__send_reminder', {}, t, 'failed').verb).toBe(
      'Failed to call send reminder'
    );
  });

  it('reads a failure out of the tool result envelope only', () => {
    expect(isFailedToolOutput('{"success": false, "message": "boom"}')).toBe(true);
    expect(isFailedToolOutput('{"error_code": "EXECUTION_FAILED"}')).toBe(true);
    expect(isFailedToolOutput('{"success": true, "message": "ok"}')).toBe(false);
    // Plain text output is output, not a failure.
    expect(isFailedToolOutput('error: command not found')).toBe(false);
    expect(isFailedToolOutput('{"success": fal')).toBe(false);
    expect(isFailedToolOutput(undefined)).toBe(false);
  });

  it('leaves untranslated headlines alone', () => {
    // A shell description is the model's own words, not a verb we own.
    expect(
      getToolSummary(
        'run_command',
        { content: 'npm test', description: 'Build the app' },
        t,
        'past'
      ).verb
    ).toBe('Build the app');
    expect(getToolSummary('some_new_tool', { query: 'q' }, t, 'past').verb).toBe(
      'Called some new tool'
    );
  });
});

describe('getRepeatedToolLabel', () => {
  it('summarizes a finished run of identical calls in the past tense', () => {
    expect(getRepeatedToolLabel('run_command', 10, t)).toBe('Ran 10 commands');
    expect(getRepeatedToolLabel('read_file', 4, t)).toBe('Read 4 files');
    expect(getRepeatedToolLabel('Bash', 3, t)).toBe('Ran 3 commands');
    expect(getRepeatedToolLabel('web_search', 2, t)).toBe('Ran 2 web searches');
  });

  it('describes a run that is still going in the present tense', () => {
    expect(getRepeatedToolLabel('run_command', 10, t, 'active')).toBe('Running 10 commands');
    expect(getRepeatedToolLabel('read_file', 4, t, 'active')).toBe('Reading 4 files');
    expect(getRepeatedToolLabel('web_search', 2, t, 'active')).toBe('Running 2 web searches');
    expect(getRepeatedToolLabel('glob_search', 5, t, 'active')).toBe('Looking for files 5 times');
  });

  it('falls back to the tool headline for tools without a repeat phrasing', () => {
    expect(getRepeatedToolLabel('speak', 3, t)).toBe('Said · 3 times');
    expect(getRepeatedToolLabel('speak', 3, t, 'active')).toBe('Saying · 3 times');
  });
});

describe('normalizeToolName', () => {
  it('maps aliases and strips mcp prefixes', () => {
    expect(normalizeToolName('WebSearch')).toBe('web_search');
    expect(normalizeToolName('bash_execute')).toBe('run_command');
    expect(normalizeToolName('mcp__my_server__do_thing')).toBe('do_thing');
    expect(normalizeToolName('read_file')).toBe('read_file');
  });
});
