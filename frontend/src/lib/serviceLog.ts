/**
 * Reading `server.log` back into records.
 *
 * The backend writes one line per record, `time | LEVEL | where | message`,
 * and everything else that reaches the file -- a traceback, a dependency
 * printing to stdout -- arrives as loose lines between them. The console shows
 * the log to answer "what went wrong", so it has to separate those two things:
 * a record can be coloured by severity and filtered, while a traceback belongs
 * with the record that announced it rather than on its own.
 */

export const LOG_LEVELS = [
  'TRACE',
  'DEBUG',
  'INFO',
  'SUCCESS',
  'WARNING',
  'ERROR',
  'CRITICAL',
] as const;

export type LogLevel = (typeof LOG_LEVELS)[number];

/** loguru's own severities, so a threshold here means what it means there. */
const SEVERITY: Record<LogLevel, number> = {
  TRACE: 5,
  DEBUG: 10,
  INFO: 20,
  SUCCESS: 25,
  WARNING: 30,
  ERROR: 40,
  CRITICAL: 50,
};

export interface LogEntry {
  /** Position in the tail; stable for as long as the tail is. */
  index: number;
  /** As printed, with or without the date depending on the writer. */
  time: string | null;
  /** Null for a line that is not a log record — a traceback's first line. */
  level: LogLevel | null;
  /** `module:function:line`, as printed. */
  source: string | null;
  message: string;
  /** Loose lines that followed this record, kept in order. */
  continuation: string[];
}

// Colour codes survive in a log captured from a terminal. The backend no
// longer writes them and the tail endpoint strips them, but an older file is
// still on disk on every machine that has run a previous version.
// eslint-disable-next-line no-control-regex -- ESC is the escape sequence
const ANSI = /\x1b\[[0-9;]*[A-Za-z]/g;

// `2026-05-04 13:47:32.481 | INFO     | suzent.server:startup:120 | Ready`
// The date is optional: a log captured from a terminal-formatted stream only
// carries the time. The message separator is `-` rather than `|` on the lines
// written during import, before the application has configured its own format.
const RECORD =
  /^(\d{4}-\d{2}-\d{2} )?(\d{2}:\d{2}:\d{2}(?:[.,]\d+)?) \| ([A-Z]+)\s* \| ([^|]*?) [|-] ([\s\S]*)$/;

function asLevel(token: string): LogLevel | null {
  return (LOG_LEVELS as readonly string[]).includes(token) ? (token as LogLevel) : null;
}

const TRACEBACK_START = /^Traceback \(most recent call last\):/;

/**
 * Split a tail into records, attaching a traceback to the record above it.
 *
 * Only a traceback is folded into the record before it, and it runs until the
 * next record: loguru decorates its frames with markers and blank lines, so
 * "indented" is not a reliable test of what is still part of one. Every other
 * loose line stands on its own, because a log also carries unrelated output
 * that merely follows a record -- a dependency printing to stdout -- and
 * swallowing a run of those hides them behind a line they have nothing to do
 * with.
 */
export function parseServiceLog(lines: readonly string[]): LogEntry[] {
  const entries: LogEntry[] = [];
  let inTraceback = false;

  const loose = (message: string): LogEntry => ({
    index: entries.length,
    time: null,
    level: null,
    source: null,
    message,
    continuation: [],
  });

  for (const line of lines) {
    const clean = line.replace(ANSI, '');
    const match = RECORD.exec(clean);
    const level = match ? asLevel(match[3]) : null;
    if (match && level) {
      inTraceback = false;
      entries.push({
        index: entries.length,
        time: (match[1] ?? '') + match[2],
        level,
        source: match[4].trim() || null,
        message: match[5],
        continuation: [],
      });
      continue;
    }

    const previous = entries[entries.length - 1];
    const starts = TRACEBACK_START.test(clean);

    if (!previous || !(starts || inTraceback)) {
      entries.push(loose(clean));
      inTraceback = starts;
      continue;
    }

    previous.continuation.push(clean);
    inTraceback = true;
  }
  return entries;
}

export interface LogFilter {
  /** Hide records less severe than this. Unlevelled lines always show. */
  minLevel?: LogLevel | null;
  /** Case-insensitive substring, matched against the whole record. */
  query?: string;
}

function matchesQuery(entry: LogEntry, needle: string): boolean {
  const haystack = [entry.time, entry.source, entry.message, ...entry.continuation]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return haystack.includes(needle);
}

export function filterServiceLog(
  entries: readonly LogEntry[],
  { minLevel = null, query = '' }: LogFilter = {}
): LogEntry[] {
  const needle = query.trim().toLowerCase();
  const floor = minLevel ? SEVERITY[minLevel] : null;
  return entries.filter((entry) => {
    // A line with no level is output that bypassed the logger — a crash on the
    // way out, most importantly. A severity filter must not bury it.
    if (floor !== null && entry.level && SEVERITY[entry.level] < floor) return false;
    if (needle && !matchesQuery(entry, needle)) return false;
    return true;
  });
}

/** How many records carry each level, for the counts beside the filter. */
export function countByLevel(entries: readonly LogEntry[]): Record<LogLevel, number> {
  const counts = Object.fromEntries(LOG_LEVELS.map((level) => [level, 0])) as Record<
    LogLevel,
    number
  >;
  for (const entry of entries) {
    if (entry.level) counts[entry.level] += 1;
  }
  return counts;
}

/** An entry back as text, for copying out of the viewer. */
export function formatEntry(entry: LogEntry): string {
  const head = [entry.time, entry.level, entry.source, entry.message]
    .filter((part) => part !== null && part !== '')
    .join(' | ');
  return [head, ...entry.continuation].join('\n');
}
