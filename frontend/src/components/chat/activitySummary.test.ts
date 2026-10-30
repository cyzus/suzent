import { describe, expect, it } from 'vitest';
import { tForLocale } from '../../i18n';
import { summarizeActivity } from './activitySummary';
const t = (key: string, params?: Record<string, unknown>): string =>
  tForLocale('zh-CN', key, params);
describe('summarizeActivity', () => {
  it('counts commands and distinct edited files', () => {
    expect(
      summarizeActivity(
        [
          { toolName: 'run_command' },
          { toolName: 'Bash' },
          { toolName: 'edit_file', args: '{"path":"a.ts"}' },
          { toolName: 'write_file', args: '{"file_path":"a.ts"}' },
          { toolName: 'edit_file', args: '{"path":"b.ts"}' },
        ],
        t
      )
    ).toBe('执行了 2 条命令 · 修改了 2 个文件');
  });
  it('does not claim failed or unknown-path edits changed files', () => {
    expect(
      summarizeActivity(
        [
          { toolName: 'edit_file', failed: true },
          { toolName: 'edit_file', args: '{' },
        ],
        t
      )
    ).toBe('1 次调用失败 · 调用了 1 次工具');
    expect(summarizeActivity([], t)).toBeUndefined();
  });
  it('names sub-agent work instead of lumping it into other tools', () => {
    expect(
      summarizeActivity(
        [
          { toolName: 'agent', args: '{"description":"Fix the build"}' },
          { toolName: 'agent_dispatch', args: '{"agent_id":"new","message":"Go"}' },
          { toolName: 'agent_read', args: '{"agent_id":"a1"}' },
          { toolName: 'agent_dispatch', args: '{"agent_id":"a1","message":"Next"}' },
          { toolName: 'render_ui' },
        ],
        t
      )
    ).toBe('委派了 2 项任务 · 与代理沟通 2 次 · 另有 1 项操作');
  });
});
