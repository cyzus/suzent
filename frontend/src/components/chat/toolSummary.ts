/**
 * Turns a tool call into a short, human-readable headline.
 *
 * Tool call pills used to show only the tool name ("web search", "read file"),
 * which tells you nothing about what the agent actually did. This module reads
 * each tool's own arguments and produces a verb + detail pair — "READ
 * ToolCallBlock.tsx", "SEARCH \"tauri window transparency\"", "RUN build the
 * app" — so a collapsed transcript is scannable without expanding anything.
 *
 * The verb is translated (rendered uppercase by the pill) and the detail is
 * verbatim argument text (rendered in normal case, so paths and queries stay
 * readable).
 */

export type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

export interface ToolSummary {
  /** Translated action label, e.g. "Read". Always present. */
  verb: string;
  /** Truncated argument detail shown next to the verb, or null. */
  detail: string | null;
  /** Untruncated "verb — detail" text for the header tooltip, or null. */
  title: string | null;
}

const DETAIL_MAX = 64;

// ---------------------------------------------------------------------------
// Value helpers
// ---------------------------------------------------------------------------

function compact(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function truncate(value: string, max = DETAIL_MAX): string {
  return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}

/** Non-empty trimmed string, or null. */
function str(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function int(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && /^-?\d+$/.test(value.trim())) return Number(value.trim());
  return null;
}

/** Last path segment, handling both POSIX and Windows separators. */
function basename(path: string): string {
  const cleaned = compact(path).replace(/[\\/]+$/, '');
  const parts = cleaned.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || cleaned;
}

/** `example.com/docs/page` — drops scheme, `www.`, query and hash. */
function shortUrl(raw: string): string {
  const cleaned = compact(raw);
  try {
    const url = new URL(cleaned);
    const host = url.hostname.replace(/^www\./, '');
    const path = url.pathname === '/' ? '' : url.pathname.replace(/\/$/, '');
    return `${host}${path}`;
  } catch {
    return cleaned.replace(/^https?:\/\//, '').replace(/^www\./, '');
  }
}

function quoted(value: string): string {
  return `“${compact(value)}”`;
}

/** First meaningful line of a shell command, ignoring blank and comment lines. */
function firstCommandLine(command: string): string {
  const lines = command.split('\n').map(line => line.trim());
  const meaningful = lines.find(line => line && !line.startsWith('#'));
  const head = meaningful ?? compact(command);
  // A trailing `&& ...` chain is noise in a one-line pill; mark it instead.
  return lines.length > 1 || head.length > DETAIL_MAX ? `${head} …` : head;
}

function firstOf(args: Args, keys: string[]): string | null {
  for (const key of keys) {
    const value = str(args[key]);
    if (value) return value;
  }
  return null;
}

/** First string found in an array of items or item objects (e.g. `tasks`). */
function firstItemLabel(value: unknown, keys: string[]): string | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const [head] = value;
  if (typeof head === 'string') return str(head);
  if (head && typeof head === 'object') {
    return firstOf(head as Args, keys);
  }
  return null;
}

// ---------------------------------------------------------------------------
// Tool name normalization
// ---------------------------------------------------------------------------

/**
 * Aliases for tools that reach the UI under a different name than the native
 * registry uses — ACP agents (Claude Code and friends) emit PascalCase names,
 * and older sessions still carry the pre-split shell tool names.
 */
const NAME_ALIASES: Record<string, string> = {
  read: 'read_file',
  write: 'write_file',
  edit: 'edit_file',
  multiedit: 'edit_file',
  notebookedit: 'edit_file',
  glob: 'glob_search',
  grep: 'grep_search',
  bash: 'run_command',
  bash_execute: 'run_command',
  shell: 'run_command',
  bashoutput: 'check_command',
  killshell: 'stop_command',
  process_manage: 'check_command',
  websearch: 'web_search',
  webfetch: 'webpage_fetch',
  task: 'agent',
  todowrite: 'create_tasks',
};

/**
 * `mcp__server__do_thing` → `do thing`, `ReadFile` → `read_file`.
 * Returns the canonical registry name when one is known.
 */
export function normalizeToolName(toolName: string): string {
  let name = toolName.trim();
  const mcp = /^mcp__[^_]+(?:_[^_]+)*?__(.+)$/.exec(name);
  if (mcp) name = mcp[1];
  // PascalCase / camelCase → snake_case, so ACP names hit the same builders.
  const snake = name
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-]+/g, '_')
    .toLowerCase();
  return NAME_ALIASES[snake] ?? snake;
}

/**
 * Lowercases a headline's first letter so it can sit inside a frame — "Search
 * the web" → "Failed to search the web". An all-caps opening (an acronym) is
 * left alone.
 */
function lowerFirst(value: string): string {
  if (/^[A-Z]{2}/.test(value)) return value;
  return value.charAt(0).toLowerCase() + value.slice(1);
}

/**
 * Whether a tool's own output says the call failed.
 *
 * Tools answer with a `ToolResult` envelope, so a failure is stated in the
 * payload rather than thrown — `success: false`, or an `error_code`. The check
 * is deliberately shallow: output that is not an envelope (plain text, a
 * truncated stream) is not a failure, it is just output.
 */
export function isFailedToolOutput(output: string | undefined): boolean {
  if (!output) return false;
  const trimmed = output.trim();
  if (!trimmed.startsWith('{')) return false;
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || typeof parsed !== 'object') return false;
    return parsed.success === false || typeof parsed.error_code === 'string';
  } catch {
    return false;
  }
}

/**
 * Puts an unrecognized tool's name into the requested tense with one frame:
 * "Call send reminder", "Calling send reminder", "Called send reminder".
 *
 * The enumerated tools each own a real verb because the phrasing is worth the
 * words — "Searched the web “x”" beats "Called web search “x”". For
 * everything else there is no verb to conjugate: the name is an identifier and
 * may not even start with a verb, so the frame carries the tense and the name
 * is left exactly as written. Three lines of translation cover every tool that
 * will ever be plugged in, and nothing can come out as "filing search" or
 * "sended reminder".
 */
function frameToolName(name: string, tense: ToolTense, t: TranslateFn): string {
  return t(`toolSummary.unknownTool.${tense}`, { name });
}

/** Fallback label when no builder matches: `do_thing` → `do thing`. */
function humanizeToolName(toolName: string): string {
  const mcp = /^mcp__([^_]+(?:_[^_]+)*?)__(.+)$/.exec(toolName.trim());
  const base = mcp ? mcp[2] : toolName.trim();
  return base
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .toLowerCase() || toolName;
}

/** Generic detail for unknown tools: the most headline-ish argument value. */
const GENERIC_DETAIL_KEYS = [
  'description',
  'title',
  'query',
  'q',
  'command',
  'cmd',
  'content',
  'file_path',
  'path',
  'pattern',
  'url',
  'name',
  'prompt',
  'text',
  'message',
  'id',
];

// ---------------------------------------------------------------------------
// Tense
// ---------------------------------------------------------------------------

/**
 * Which form of a tool's verb to use.
 *
 * A pill is read at three different moments and wants a different form at each:
 * while the agent is asking permission it is a proposal ("Run command"), while
 * the call is in flight it is happening now ("Running npm test"), and once the
 * output has landed it is a record of what was done ("Ran npm test"). Every
 * label in this module — single calls and repeat summaries alike — takes the
 * same three-way choice so a transcript never mixes the two readings.
 */
export type ToolTense = 'imperative' | 'active' | 'past' | 'failed';

const TENSE_GROUPS: Record<ToolTense, string> = {
  imperative: 'verbs',
  active: 'verbsActive',
  past: 'verbsPast',
  // A failure is framed rather than conjugated — see `getToolSummary`.
  failed: 'verbs',
};

/**
 * Wraps a translate function so every `toolSummary.verbs.*` lookup inside the
 * builders resolves to the requested tense instead. Doing it here keeps the
 * thirty-odd builders free of tense handling; a verb missing from a tensed set
 * quietly falls back to its base form rather than rendering a raw key.
 */
function withTense(t: TranslateFn, tense: ToolTense): TranslateFn {
  if (tense === 'imperative') return t;
  const prefix = 'toolSummary.verbs.';
  const group = TENSE_GROUPS[tense];
  return (key, params) => {
    if (!key.startsWith(prefix)) return t(key, params);
    const tensedKey = `toolSummary.${group}.${key.slice(prefix.length)}`;
    const tensed = t(tensedKey, params);
    return tensed === tensedKey ? t(key, params) : tensed;
  };
}

// ---------------------------------------------------------------------------
// Per-tool builders
// ---------------------------------------------------------------------------

type Args = Record<string, unknown>;

interface Built {
  /** Resolved headline text, e.g. "Search the web". */
  verb: string;
  detail?: string | null;
}

type Builder = (args: Args, t: TranslateFn) => Built;

/** Longest a model-written description may be before it stops being a headline. */
const VERB_MAX = 44;

function verb(t: TranslateFn, key: string, params?: Record<string, unknown>): string {
  return t(`toolSummary.verbs.${key}`, params);
}

/**
 * Shell tools carry a model-written description ("Build the app"). That reads
 * far better as the headline than the command line does, so it takes the verb
 * slot and the command itself becomes the supporting detail.
 */
function shellSummary(args: Args, t: TranslateFn, key: 'run' | 'start'): Built {
  const description = str(args.description);
  const command = firstOf(args, ['content', 'command', 'cmd']);
  const commandLine = command ? firstCommandLine(command) : null;
  if (description) {
    return { verb: truncate(compact(description), VERB_MAX), detail: commandLine };
  }
  return { verb: verb(t, key), detail: commandLine };
}

const BUILDERS: Record<string, Builder> = {
  read_file: (args, t) => {
    const path = str(args.file_path);
    const offset = int(args.offset);
    if (!path) return { verb: verb(t, 'read') };
    const at = offset && offset > 0 ? `:${offset}` : '';
    return { verb: verb(t, 'read'), detail: `${basename(path)}${at}` };
  },

  write_file: (args, t) => ({
    verb: verb(t, 'write'),
    detail: str(args.file_path) ? basename(str(args.file_path)!) : null,
  }),

  edit_file: (args, t) => ({
    verb: verb(t, 'edit'),
    detail: str(args.file_path) ? basename(str(args.file_path)!) : null,
  }),

  glob_search: (args, t) => ({ verb: verb(t, 'findFiles'), detail: str(args.pattern) }),

  grep_search: (args, t) => {
    const pattern = str(args.pattern);
    const scope = str(args.include) ?? (str(args.path) ? basename(str(args.path)!) : null);
    if (!pattern) return { verb: verb(t, 'searchCode') };
    return {
      verb: verb(t, 'searchCode'),
      detail: scope
        ? t('toolSummary.inScope', { value: quoted(pattern), scope })
        : quoted(pattern),
    };
  },

  run_command: (args, t) => shellSummary(args, t, 'run'),
  start_command: (args, t) => shellSummary(args, t, 'start'),

  check_command: (args, t) => ({ verb: verb(t, 'checkOutput'), detail: str(args.command_id) }),

  stop_command: (args, t) => ({ verb: verb(t, 'stopCommand'), detail: str(args.command_id) }),

  browser_action: (args, t) => {
    const command = str(args.command);
    const target = firstOf(
      (args.arguments && typeof args.arguments === 'object' && !Array.isArray(args.arguments)
        ? args.arguments
        : {}) as Args,
      ['url', 'selector', 'text', 'query'],
    );
    const detail = [command, target && shortUrl(target)].filter(Boolean).join(' · ');
    return { verb: verb(t, 'browser'), detail: detail || null };
  },

  webpage_fetch: (args, t) => ({
    verb: verb(t, 'openPage'),
    detail: str(args.url) ? shortUrl(str(args.url)!) : null,
  }),

  web_search: (args, t) => ({
    verb: verb(t, 'searchWeb'),
    detail: str(args.query) ? quoted(str(args.query)!) : null,
  }),

  ask_question: (args, t) => {
    const question = firstItemLabel(args.questions, ['question', 'header', 'text']);
    return { verb: verb(t, 'ask'), detail: question ? compact(question) : null };
  },

  manage_goal: (args, t) => {
    const action = str(args.action);
    const objective = str(args.objective) ?? str(args.subgoal_text);
    const key = action === 'create' ? 'setGoal' : action === 'complete' ? 'finishGoal' : 'goal';
    return { verb: verb(t, key), detail: objective ? compact(objective) : null };
  },

  create_tasks: (args, t) => {
    const tasks = Array.isArray(args.tasks) ? args.tasks : [];
    const first = firstItemLabel(args.tasks, ['title', 'description', 'name', 'content']);
    const label = tasks.length > 1
      ? verb(t, 'addTasks', { count: tasks.length })
      : verb(t, 'addTask');
    return { verb: label, detail: first ? compact(first) : null };
  },

  update_task: (args, t) => {
    const id = str(args.task_id);
    const status = str(args.status);
    const detail = [id, status].filter(Boolean).join(' → ');
    return { verb: verb(t, 'updateTask'), detail: detail || null };
  },

  list_tasks: (args, t) => ({
    verb: verb(t, 'listTasks'),
    detail: str(args.status) ?? str(args.assignee),
  }),

  render_ui: (args, t) => ({
    verb: verb(t, 'show'),
    detail: str(args.title) ?? str(args.component),
  }),

  generate_image: (args, t) => ({
    verb: verb(t, 'makeImage'),
    detail: str(args.prompt) ? quoted(str(args.prompt)!) : null,
  }),

  analyze_image: (args, t) => ({
    verb: verb(t, 'lookAtImage'),
    detail: str(args.image_path) ? basename(str(args.image_path)!) : null,
  }),

  speak: (args, t) => ({
    verb: verb(t, 'say'),
    detail: str(args.text) ? quoted(str(args.text)!) : str(args.prompt),
  }),

  social_message: (args, t) => {
    if (args.list_contacts === true) return { verb: verb(t, 'listContacts') };
    const recipient = str(args.recipient);
    const channel = str(args.channel);
    const detail = recipient && channel
      ? t('toolSummary.onChannel', { value: recipient, channel })
      : recipient ?? channel;
    return { verb: verb(t, 'sendMessage'), detail };
  },

  skill_execute: (args, t) => ({ verb: verb(t, 'useSkill'), detail: str(args.skill_name) }),

  memory_search: (args, t) => ({
    verb: verb(t, 'searchMemory'),
    detail: str(args.query) ? quoted(str(args.query)!) : null,
  }),

  session_search: (args, t) => ({
    verb: verb(t, 'searchChats'),
    detail: str(args.query) ? quoted(str(args.query)!) : null,
  }),

  // Like the shell tools: the job the sub-agent was given is the headline, and
  // which agent got it is the supporting detail.
  agent: (args, t) => {
    const description = str(args.description);
    const type = str(args.subagent_type);
    const who = type
      ? t('toolSummary.namedAgent', { type })
      : t('toolSummary.anyAgent');
    if (description) {
      return { verb: truncate(compact(description), VERB_MAX), detail: who };
    }
    return { verb: verb(t, 'delegate'), detail: who };
  },

  agent_list: (_args, t) => ({ verb: verb(t, 'listAgents') }),
  agent_read: (args, t) => ({ verb: verb(t, 'checkAgent'), detail: str(args.agent_id) }),
  agent_send: (args, t) => {
    const id = str(args.agent_id);
    const message = str(args.message);
    const detail = id && message ? `${id} · ${compact(message)}` : id ?? (message && compact(message));
    return { verb: verb(t, 'messageAgent'), detail: detail || null };
  },
  agent_stop: (args, t) => ({ verb: verb(t, 'stopAgent'), detail: str(args.agent_id) }),
};

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

/**
 * Build the pill headline for a tool call.
 *
 * Falls back to the humanized tool name plus its most headline-ish argument
 * when the tool has no dedicated builder (MCP tools, new tools, ACP agents).
 */
export function getToolSummary(
  toolName: string,
  parsedArgs: Record<string, unknown> | null | undefined,
  t: TranslateFn,
  tense: ToolTense = 'imperative',
): ToolSummary {
  const args = parsedArgs && typeof parsedArgs === 'object' && !Array.isArray(parsedArgs)
    ? parsedArgs
    : {};
  const canonical = normalizeToolName(toolName);
  const builder = BUILDERS[canonical];

  let headline: string;
  let rawDetail: string | null;

  // A failure wraps the proposal form — "Run npm test" → "Failed to run npm
  // test" — rather than owning a fourth set of verbs. One frame says the same
  // thing for every tool, including the ones we do not enumerate.
  const built = tense === 'failed' ? 'imperative' : tense;

  if (builder) {
    const summary = builder(args, withTense(t, built));
    headline = summary.verb;
    rawDetail = summary.detail ? compact(summary.detail) : null;
  } else {
    headline = frameToolName(humanizeToolName(toolName), built, t);
    const generic = firstOf(args, GENERIC_DETAIL_KEYS);
    rawDetail = generic ? compact(generic) : null;
  }

  if (tense === 'failed') headline = t('toolSummary.failed', { verb: lowerFirst(headline) });

  return {
    verb: headline,
    detail: rawDetail ? truncate(rawDetail) : null,
    title: rawDetail ? `${headline} — ${rawDetail}` : headline,
  };
}

/** Repeat-label key per tool, for runs of the same tool back to back. */
const REPEAT_KEYS: Record<string, string> = {
  read_file: 'read',
  write_file: 'write',
  edit_file: 'edit',
  run_command: 'run',
  start_command: 'run',
  web_search: 'searchWeb',
  grep_search: 'searchCode',
  glob_search: 'findFiles',
  webpage_fetch: 'openPage',
  browser_action: 'browser',
};

/**
 * Label for a run of back-to-back calls to the same tool, e.g. "Running 10
 * commands". Ten separate pills all reading "Run …" say less than one line
 * saying how many there were.
 *
 * Takes the same tense as a single call: a streak still running reads
 * "Running 10 commands", a finished one "Ran 10 commands". A proposal is never
 * a streak, so `imperative` reads back as the past like any finished run.
 */
export function getRepeatedToolLabel(
  toolName: string,
  count: number,
  t: TranslateFn,
  tense: ToolTense = 'past',
): string {
  const group = tense === 'active' ? 'repeatsActive' : 'repeats';
  const key = REPEAT_KEYS[normalizeToolName(toolName)];
  if (key) return t(`toolSummary.${group}.${key}`, { count });
  return t(`toolSummary.${group}.generic`, {
    name: getToolSummary(toolName, null, t, tense).verb,
    count,
  });
}
