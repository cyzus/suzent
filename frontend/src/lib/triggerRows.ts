import type { Message } from '../types/api';
import { focalRequestText } from './focalAgent';
import { isQuietReply } from './quietReply';

export type TriggerKind = 'agent' | 'scheduled' | 'goal' | 'other';

export type TriggerState = 'replied' | 'quiet' | 'pending';

export interface ParsedTrigger {
  kind: TriggerKind;
  /** Who or what started the turn: a chat title, a job name, or the first line. */
  source: string;
  /** The sending chat's id, for agent messages. */
  reference?: string;
  body: string;
  /** Rows with the same key come from the same source and can be merged. */
  key: string;
}

export interface TriggerEntry {
  index: number;
  trigger: ParsedTrigger;
  timestamp?: string;
  /** replied: the agent answered; quiet: it answered with nothing for the user;
   *  pending: no answer yet. */
  state: TriggerState;
}

export interface TriggerPlan {
  /** Trigger rows folded into a later row, and the silent replies between them. */
  skipIndices: Set<number>;
  /** Trigger runs that render as their own row, keyed by the row's index. */
  rows: Map<number, TriggerEntry[]>;
  /** Trigger runs shown as a reference on the reply they started, keyed by the reply's index. */
  replies: Map<number, TriggerEntry[]>;
}

const INBOX_MARKER = /<!--\s*suzent-agent-inbox:[\s\S]*?-->/gi;
const AGENT_HEADER = /^\[Agent message from (.+) \(([^)\n]+)\)\]\s*/;
const SCHEDULED_HEADER = /^\*\*Scheduled Task:\s*(.+?)\*\*\s*/;
const GOAL_HEADER = /^\[Goal mode\]\s*/;

export function parseTrigger(content: string | undefined | null): ParsedTrigger {
  const raw = (content ?? '').replace(INBOX_MARKER, '').trim();

  const agent = raw.match(AGENT_HEADER);
  if (agent) {
    const source = agent[1].trim();
    return {
      kind: 'agent',
      source,
      reference: agent[2].trim(),
      body: raw.slice(agent[0].length).trim(),
      key: `agent:${agent[2].trim()}`,
    };
  }

  const scheduled = raw.match(SCHEDULED_HEADER);
  if (scheduled) {
    const source = scheduled[1].trim();
    return {
      kind: 'scheduled',
      source,
      body: raw.slice(scheduled[0].length).trim(),
      key: `scheduled:${source}`,
    };
  }

  if (GOAL_HEADER.test(raw)) {
    return { kind: 'goal', source: '', body: raw.replace(GOAL_HEADER, '').trim(), key: 'goal' };
  }

  const [firstLine = '', ...rest] = raw.split('\n');
  const bold = firstLine.trim().match(/^\*\*(.+?)\*\*$/);
  const source = (bold ? bold[1] : firstLine).trim();
  return { kind: 'other', source, body: rest.join('\n').trim(), key: `other:${source}` };
}

/**
 * The first line of the body as plain text, for a one-line preview. Headings
 * often repeat the sender's name, so prose wins over them.
 */
export function triggerPreview(body: string): string {
  const lines = body
    .split('\n')
    .map((value) => value.trim())
    .filter((value) => value && !/^[-*_=#\s]+$/.test(value));
  const line = lines.find((value) => !value.startsWith('#')) ?? lines[0];
  if (!line) return '';
  return line
    .replace(/^#+\s*/, '')
    .replace(/^[-*+>]\s+/, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .trim();
}

/** An assistant row the user sees nothing of: only reasoning or a quiet reply. */
export function isSilentReply(message: Message): boolean {
  if (message.role !== 'assistant') return false;
  if (message.parts && message.parts.length > 0) {
    return message.parts.every(
      (part) =>
        part.type === 'reasoning' ||
        part.type === 'citation-sources' ||
        (part.type === 'text' && (!part.text?.trim() || isQuietReply(part.text)))
    );
  }
  const content = message.content?.trim() ?? '';
  return !content || isQuietReply(content);
}

function isPlainTrigger(message: Message): boolean {
  return message.role === 'system_triggered' && !focalRequestText(message.content);
}

/**
 * Fold background triggers into as few rows as possible. Repeats of the same
 * trigger that the agent answered with nothing merge into one row, and a run
 * the agent answered moves onto that answer as a reference line.
 *
 * `rows` may end with a live message; it never counts as silent or as a
 * finished answer, so a trigger right before it keeps its own row.
 */
export function buildTriggerPlan(
  rows: Message[],
  hidden: ReadonlySet<number>,
  liveIndex?: number
): TriggerPlan {
  const skipIndices = new Set<number>();
  const rowRuns = new Map<number, TriggerEntry[]>();
  const replies = new Map<number, TriggerEntry[]>();

  const nextShown = (from: number): number => {
    let idx = from;
    while (idx < rows.length && hidden.has(idx)) idx += 1;
    return idx;
  };

  let i = 0;
  while (i < rows.length) {
    if (hidden.has(i) || !isPlainTrigger(rows[i])) {
      i += 1;
      continue;
    }

    const run: TriggerEntry[] = [];
    let cursor = i;
    while (true) {
      const message = rows[cursor];
      const trigger = parseTrigger(message.content);
      const entry: TriggerEntry = {
        index: cursor,
        trigger,
        timestamp: message.timestamp,
        state: 'pending',
      };
      run.push(entry);

      // Gather the silent replies after this trigger.
      const silent: number[] = [];
      let next = nextShown(cursor + 1);
      while (next < rows.length && next !== liveIndex && isSilentReply(rows[next])) {
        silent.push(next);
        next = nextShown(next + 1);
      }
      if (silent.length > 0) entry.state = 'quiet';

      const continues =
        silent.length > 0 &&
        next < rows.length &&
        isPlainTrigger(rows[next]) &&
        parseTrigger(rows[next].content).key === trigger.key;
      if (!continues) {
        for (const idx of silent) skipIndices.add(idx);
        cursor = next;
        break;
      }
      skipIndices.add(cursor);
      for (const idx of silent) skipIndices.add(idx);
      cursor = next;
    }

    const last = run[run.length - 1];
    const following = last.state === 'pending' ? nextShown(last.index + 1) : rows.length;
    if (
      following < rows.length &&
      following !== liveIndex &&
      rows[following].role === 'assistant'
    ) {
      last.state = 'replied';
      skipIndices.add(last.index);
      replies.set(following, run);
    } else {
      rowRuns.set(last.index, run);
    }
    i = Math.max(cursor, last.index + 1);
  }

  return { skipIndices, rows: rowRuns, replies };
}
