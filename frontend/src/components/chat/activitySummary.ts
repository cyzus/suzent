import { normalizeToolName, type TranslateFn } from './toolSummary';

export interface ActivitySummaryTool {
  toolName?: string;
  args?: string;
  failed?: boolean;
  running?: boolean;
  toolCallId?: string;
  output?: string;
}

export function summarizeActivity(
  tools: ActivitySummaryTool[],
  t: TranslateFn
): string | undefined {
  const counts = new Map<string, number>();
  const files = { read: new Set<string>(), changed: new Set<string>() };
  const add = (key: string): void => {
    counts.set(key, (counts.get(key) ?? 0) + 1);
  };
  for (const tool of tools) {
    if (tool.failed) {
      add('failed');
      continue;
    }
    if (tool.running) {
      add('running');
      continue;
    }
    const name = normalizeToolName(tool.toolName ?? '');
    if (['run_command', 'start_command'].includes(name)) {
      add('commands');
      continue;
    }
    if (
      ['web_search', 'glob_search', 'grep_search', 'memory_search', 'session_search'].includes(name)
    ) {
      add('searches');
      continue;
    }
    if (['read_file', 'write_file', 'edit_file'].includes(name)) {
      let args: Record<string, unknown> = {};
      try {
        const parsed: unknown = JSON.parse(tool.args || '{}');
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
          args = parsed as Record<string, unknown>;
      } catch {
        /* Arguments can be incomplete in restored calls. */
      }
      const path = [args.file_path, args.path, args.filePath, args.filename].find(
        (value) => typeof value === 'string' && value.trim()
      );
      if (typeof path === 'string') {
        const kind = name === 'read_file' ? 'read' : 'changed';
        const normalized = path.trim().replace(/\\/g, '/').replace(/^\.\//, '');
        if (!files[kind].has(normalized)) {
          files[kind].add(normalized);
          add(kind);
        }
        continue;
      }
    }
    add('other');
  }
  return (
    [...counts].map(([key, count]) => t(`activityRail.summary.${key}`, { count })).join(' · ') ||
    undefined
  );
}
