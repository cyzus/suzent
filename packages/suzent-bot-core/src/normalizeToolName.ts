/**
 * Aliases for tools that reach the UI under a different name than the native
 * registry uses — ACP agents emit PascalCase names, and older sessions still
 * carry the pre-split shell tool names.
 */
const NAME_ALIASES: Record<string, string> = {
  read: "read_file",
  write: "write_file",
  edit: "edit_file",
  multiedit: "edit_file",
  notebookedit: "edit_file",
  glob: "glob_search",
  grep: "grep_search",
  bash: "run_command",
  bash_execute: "run_command",
  shell: "run_command",
  bashoutput: "check_command",
  killshell: "stop_command",
  process_manage: "check_command",
  websearch: "web_search",
  webfetch: "webpage_fetch",
  web_fetch: "webpage_fetch",
  task: "agent",
  todowrite: "create_tasks",
};

/**
 * `mcp__server__do_thing` → `do_thing`, `ReadFile` → `read_file`.
 * Returns the canonical registry name when one is known.
 */
export function normalizeToolName(toolName: string): string {
  let name = toolName.trim();
  const mcp = /^mcp__[^_]+(?:_[^_]+)*?__(.+)$/.exec(name);
  if (mcp) name = mcp[1];
  const snake = name
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[\s-]+/g, "_")
    .toLowerCase();
  return NAME_ALIASES[snake] ?? snake;
}
