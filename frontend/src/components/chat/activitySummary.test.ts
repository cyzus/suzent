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
    ).toBe('1 次调用失败 · 调用了 1 次其他工具');
    expect(summarizeActivity([], t)).toBeUndefined();
  });
});
