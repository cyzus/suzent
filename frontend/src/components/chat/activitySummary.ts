import { normalizeToolName, type TranslateFn } from './toolSummary';

export interface ActivitySummaryTool {
  toolName?: string;
  args?: string;
  failed?: boolean;
  running?: boolean;
  toolCallId?: string;
  output?: string;
}

const CATEGORIES: Record<string, string> = {
  run_command: 'commands',
  start_command: 'commands',
  web_search: 'searches',
  glob_search: 'searches',
  grep_search: 'searches',
  memory_search: 'searches',
  session_search: 'searches',
  webpage_fetch: 'web',
  browser_action: 'web',
  agent: 'delegated',
  agent_list: 'agents',
  agent_read: 'agents',
  agent_send: 'agents',
  agent_stop: 'agents',
  create_tasks: 'tasks',
  update_task: 'tasks',
  list_tasks: 'tasks',
  manage_goal: 'tasks',
  memory_update: 'memory',
  update_notes: 'memory',
  skill_execute: 'skills',
};

function parseArgs(raw: string | undefined): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(raw || '{}');
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
      return parsed as Record<string, unknown>;
  } catch {
    /* Arguments can be incomplete in restored calls. */
  }
  return {};
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
    if (name === 'agent_dispatch') {
      add(parseArgs(tool.args).agent_id === 'new' ? 'delegated' : 'agents');
      continue;
    }
    const category = CATEGORIES[name];
    if (category) {
      add(category);
      continue;
    }
    if (['read_file', 'write_file', 'edit_file'].includes(name)) {
      const args = parseArgs(tool.args);
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
  // "Other" only reads right beside something it is other than.
  const others = counts.get('other');
  if (others && ![...counts.keys()].some((key) => !['other', 'failed', 'running'].includes(key))) {
    counts.delete('other');
    counts.set('tools', others);
  }
  return (
    [...counts].map(([key, count]) => t(`activityRail.summary.${key}`, { count })).join(' · ') ||
    undefined
  );
}
