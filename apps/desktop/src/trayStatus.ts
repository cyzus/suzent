/**
 * Live status in the tray: chats waiting on the user, chats running, and
 * whether the backend answers at all. Pure functions here; tray.ts draws it.
 */

export interface ChatRow {
  chatId: string;
  title?: string | null;
  state: string;
  waitingKind?: string | null;
}

export type Snapshot =
  | { kind: 'starting' }
  | { kind: 'unreachable' }
  | { kind: 'ready'; waiting: ChatRow[]; running: ChatRow[] };

export const MAX_LISTED = 4;
const TITLE_MAX_CHARS = 28;

export function snapshotFromRows(rows: ChatRow[]): Snapshot {
  return {
    kind: 'ready',
    waiting: rows.filter((row) => row.state === 'waiting'),
    running: rows.filter((row) => row.state === 'running'),
  };
}

export function needsAttention(snapshot: Snapshot): boolean {
  return snapshot.kind === 'ready' && snapshot.waiting.length > 0;
}

export function sameSnapshot(a: Snapshot | null, b: Snapshot): boolean {
  return a !== null && JSON.stringify(a) === JSON.stringify(b);
}

export function isChinese(language: string): boolean {
  return language.trim().toLowerCase().startsWith('zh');
}

function pick(zh: boolean, chinese: string, english: string): string {
  return zh ? chinese : english;
}

export function waitingKindLabel(kind: string | null | undefined, zh: boolean): string {
  switch (kind) {
    case 'question':
      return pick(zh, '有问题问你', 'has a question');
    case 'approval':
      return pick(zh, '等你批准', 'needs approval');
    case 'task':
      return pick(zh, '任务卡住了', 'task is blocked');
    default:
      return pick(zh, '等你回复', 'waiting for you');
  }
}

export function clipTitle(title: string | null | undefined, fallback: string): string {
  const trimmed = title?.trim() || fallback;
  const chars = Array.from(trimmed);
  if (chars.length <= TITLE_MAX_CHARS) return trimmed;
  return `${chars.slice(0, TITLE_MAX_CHARS - 1).join('')}…`;
}

export function tooltip(snapshot: Snapshot, zh: boolean): string {
  if (snapshot.kind === 'starting') return `SUZENT · ${pick(zh, '正在启动…', 'starting…')}`;
  if (snapshot.kind === 'unreachable')
    return `SUZENT · ${pick(zh, '后端未连接', 'backend offline')}`;
  const waiting = snapshot.waiting.length;
  const running = snapshot.running.length;
  if (waiting === 0 && running === 0) return `SUZENT · ${pick(zh, '一切就绪', 'all clear')}`;
  const parts: string[] = [];
  if (waiting > 0) parts.push(zh ? `${waiting} 个聊天在等你` : `${waiting} waiting for you`);
  if (running > 0) parts.push(zh ? `${running} 个正在运行` : `${running} running`);
  return `SUZENT · ${parts.join(' · ')}`;
}

export type MenuEntry =
  | { type: 'label'; label: string }
  | { type: 'chat'; label: string; chatId: string }
  | { type: 'separator' }
  | { type: 'show'; label: string }
  | { type: 'quit'; label: string };

export function menuEntries(snapshot: Snapshot, zh: boolean): MenuEntry[] {
  const entries: MenuEntry[] = [];
  const untitled = pick(zh, '未命名聊天', 'Untitled chat');
  if (snapshot.kind === 'starting') {
    entries.push({ type: 'label', label: pick(zh, '◌ 后端正在启动…', '◌ Backend starting…') });
  } else if (snapshot.kind === 'unreachable') {
    entries.push({ type: 'label', label: pick(zh, '⚠ 后端未连接', '⚠ Backend offline') });
  } else {
    const { waiting, running } = snapshot;
    if (waiting.length === 0 && running.length === 0) {
      entries.push({ type: 'label', label: pick(zh, '✓ 没有等你处理的事', '✓ Nothing needs you') });
    }
    if (waiting.length > 0) {
      entries.push({
        type: 'label',
        label: zh ? `● 等你处理（${waiting.length}）` : `● Needs you (${waiting.length})`,
      });
      for (const row of waiting.slice(0, MAX_LISTED)) {
        entries.push({
          type: 'chat',
          chatId: row.chatId,
          label: `    ${clipTitle(row.title, untitled)} — ${waitingKindLabel(row.waitingKind, zh)}`,
        });
      }
    }
    if (running.length > 0) {
      if (waiting.length > 0) entries.push({ type: 'separator' });
      entries.push({
        type: 'label',
        label: zh ? `▶ 正在运行（${running.length}）` : `▶ Running (${running.length})`,
      });
      for (const row of running.slice(0, MAX_LISTED)) {
        entries.push({
          type: 'chat',
          chatId: row.chatId,
          label: `    ${clipTitle(row.title, untitled)}`,
        });
      }
    }
  }
  entries.push({ type: 'separator' });
  entries.push({ type: 'show', label: pick(zh, '打开', 'Open') });
  entries.push({ type: 'quit', label: pick(zh, '退出', 'Quit') });
  return entries;
}

const BADGE_RADIUS = 0.19;
const BADGE_GAP = 0.06;
const OFFLINE_OPACITY = 0.45;
/** The attention dot, in the BGRA order of Electron's native bitmaps. */
export const ATTENTION_BGRA: [number, number, number] = [61, 77, 255];

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value));

/**
 * A copy of a BGRA bitmap with a coloured dot in the bottom-right corner and
 * a transparent gap around it, so the dot reads on any tray background.
 */
export function badged(
  bitmap: Buffer,
  width: number,
  height: number,
  color: [number, number, number] = ATTENTION_BGRA
): Buffer {
  const out = Buffer.from(bitmap);
  const size = Math.min(width, height);
  const radius = size * BADGE_RADIUS;
  const gap = Math.max(size * BADGE_GAP, 1);
  const cx = width - radius - 0.5;
  const cy = height - radius - 0.5;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const distance = Math.hypot(x + 0.5 - cx, y + 0.5 - cy);
      const pixel = (y * width + x) * 4;
      const keep = clamp01(distance - radius - gap + 0.5);
      const dot = clamp01(radius - distance + 0.5);
      const under = (out[pixel + 3] / 255) * keep;
      const alpha = dot + under * (1 - dot);
      if (alpha <= 0) {
        out.fill(0, pixel, pixel + 4);
        continue;
      }
      for (let channel = 0; channel < 3; channel += 1) {
        const over = color[channel] * dot;
        const below = out[pixel + channel] * under * (1 - dot);
        out[pixel + channel] = Math.round((over + below) / alpha);
      }
      out[pixel + 3] = Math.round(alpha * 255);
    }
  }
  return out;
}

export function faded(bitmap: Buffer): Buffer {
  const out = Buffer.from(bitmap);
  for (let pixel = 3; pixel < out.length; pixel += 4) {
    out[pixel] = Math.round(out[pixel] * OFFLINE_OPACITY);
  }
  return out;
}

export async function fetchSnapshot(port: number | null): Promise<Snapshot> {
  if (!port) return { kind: 'starting' };
  try {
    const response = await fetch(`http://127.0.0.1:${port}/focal/chats`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return { kind: 'unreachable' };
    const payload = (await response.json()) as { chats?: ChatRow[] };
    return snapshotFromRows(Array.isArray(payload.chats) ? payload.chats : []);
  } catch {
    return { kind: 'unreachable' };
  }
}
