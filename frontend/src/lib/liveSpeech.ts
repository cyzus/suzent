import type { AGUIPart } from '../types/agui';

/** Probe snapshots are history; subsequent unseen results are live, even after reconnect. */
export class LiveSpeechTracker {
  private seen = new Set<string>();
  private first = true;
  private seeded: Set<string>;
  constructor(
    private probe: boolean,
    seed: AGUIPart[] = []
  ) {
    this.seeded = new Set(
      seed
        .filter((part) => part.type === 'tool' && part.output)
        .map((part) => part.toolCallId || '')
    );
  }
  collect(parts: AGUIPart[], runId: string, reset: boolean): AGUIPart[] {
    const historical = this.first && this.probe && reset;
    this.first = false;
    return parts.filter((part) => {
      if (part.type !== 'tool' || part.toolName !== 'speak' || !part.output || !part.toolCallId)
        return false;
      const id = `${runId}:${part.toolCallId}`;
      if (this.seen.has(id)) return false;
      this.seen.add(id);
      return !historical && !this.seeded.has(part.toolCallId);
    });
  }
}
