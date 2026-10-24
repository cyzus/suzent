import { int16ToFloat32 } from './pcm';

type AudioContextConstructor = new (options?: AudioContextOptions) => AudioContext;

export class PcmPlayer {
  readonly context: AudioContext;
  onDrained?: () => void;
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private firstStart: number | null = null;
  private playedBeforeFlush = 0;

  constructor(
    readonly sampleRate: number,
    Context: AudioContextConstructor = window.AudioContext
  ) {
    this.context = new Context({ sampleRate });
  }

  enqueue(data: ArrayBuffer): void {
    const samples = int16ToFloat32(
      data.byteLength % 2 === 0 ? data : data.slice(0, data.byteLength - 1)
    );
    if (!samples.length) return;
    const buffer = this.context.createBuffer(1, samples.length, this.sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    const now = this.context.currentTime;
    const start = Math.max(this.nextStart, now + 0.03);
    if (this.firstStart === null) {
      this.firstStart = start;
      this.playedBeforeFlush = 0;
    }
    this.nextStart = start + buffer.duration;
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source);
      if (!this.sources.size) {
        this.nextStart = 0;
        this.firstStart = null;
        this.playedBeforeFlush = 0;
        this.onDrained?.();
      }
    };
    source.start(start);
  }

  /** Whether Suzent's voice is coming out of the speakers right now. */
  audible(): boolean {
    return (
      this.sources.size > 0 &&
      this.firstStart !== null &&
      this.context.currentTime >= this.firstStart
    );
  }

  playedMs(): number {
    if (this.firstStart === null) return Math.round(this.playedBeforeFlush);
    const elapsed = Math.max(0, this.context.currentTime - this.firstStart) * 1000;
    const scheduled = Math.max(0, this.nextStart - this.firstStart) * 1000;
    return Math.round(Math.min(elapsed, scheduled));
  }

  flush(): void {
    this.playedBeforeFlush = this.playedMs();
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // A source may already have ended between iteration and stop.
      }
    }
    this.sources.clear();
    this.nextStart = 0;
    this.firstStart = null;
  }

  async close(): Promise<void> {
    this.flush();
    await this.context.close();
  }
}
