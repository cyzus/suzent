export type SpeechState = 'idle' | 'queued' | 'playing' | 'blocked';
type Finish = (blocked?: boolean) => void;
export interface SpeechJob {
  id: string;
  start: (finish: Finish) => () => void;
}

/** One queue survives transient-to-persisted message remounts, but never chat switches. */
export class SpeechQueue {
  private jobs: SpeechJob[] = [];
  private active: SpeechJob | null = null;
  private cleanup: (() => void) | null = null;
  private states = new Map<string, SpeechState>();
  private seen = new Set<string>();
  private listeners = new Set<() => void>();
  private enabled = true;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  state = (id: string): SpeechState => this.states.get(id) || 'idle';
  private update(id: string, state: SpeechState): void {
    this.states.set(id, state);
    this.listeners.forEach((listener) => listener());
  }
  enqueue(job: SpeechJob, automatic = false): void {
    if (automatic) {
      if (this.seen.has(job.id)) return;
      this.seen.add(job.id);
      if (!this.enabled) return;
    }
    if (this.active?.id === job.id || this.jobs.some((item) => item.id === job.id)) return;
    this.jobs.push(job);
    this.update(job.id, 'queued');
    this.next();
  }
  private next(): void {
    if (this.active || !this.jobs.length) return;
    const job = this.jobs.shift()!;
    this.active = job;
    this.update(job.id, 'playing');
    let starting = true;
    let immediate: boolean | undefined;
    const finish: Finish = (blocked = false) => {
      if (starting) {
        immediate = blocked;
        return;
      }
      if (this.active !== job) return;
      this.active = null;
      const cleanup = this.cleanup;
      this.cleanup = null;
      cleanup?.();
      this.update(job.id, blocked ? 'blocked' : 'idle');
      this.next();
    };
    try {
      const cleanup = job.start(finish);
      this.cleanup = cleanup;
      starting = false;
      if (immediate !== undefined) finish(immediate);
    } catch {
      starting = false;
      finish(true);
    }
  }
  stop(id: string): void {
    this.jobs = this.jobs.filter((job) => job.id !== id);
    if (this.active?.id === id) {
      this.active = null;
      const cleanup = this.cleanup;
      this.cleanup = null;
      cleanup?.();
    }
    this.update(id, 'idle');
    this.next();
  }
  reset(): void {
    this.jobs = [];
    this.active = null;
    const cleanup = this.cleanup;
    this.cleanup = null;
    cleanup?.();
    this.states.clear();
    this.seen.clear();
    this.listeners.forEach((listener) => listener());
  }
  setAutoplay(enabled: boolean): void {
    this.enabled = enabled;
    if (!enabled) {
      // Preserve seen IDs so re-enabling never replays an earlier result.
      // Only automatic jobs are cancelled; manual playback keeps going.
      for (const job of this.jobs) if (this.seen.has(job.id)) this.update(job.id, 'idle');
      this.jobs = this.jobs.filter((job) => !this.seen.has(job.id));
      if (this.active && this.seen.has(this.active.id)) this.stop(this.active.id);
    }
  }
}

export const speechQueue = new SpeechQueue();

export function speechId(metadata: Record<string, unknown>, src?: string): string {
  return String(metadata.speech_id || src || JSON.stringify(metadata));
}

export function createSpeechJob(metadata: Record<string, unknown>, src?: string): SpeechJob {
  return {
    id: speechId(metadata, src),
    start(finish) {
      if (src) {
        const audio = new Audio(src);
        let disposed = false;
        audio.volume = Math.max(0, Math.min(1, Number(metadata.volume ?? 1)));
        audio.onended = () => finish();
        audio.onerror = () => finish(true);
        void audio.play().catch(() => {
          if (!disposed) finish(true);
        });
        return () => {
          disposed = true;
          audio.onended = null;
          audio.onerror = null;
          audio.pause();
          audio.removeAttribute('src');
          audio.load();
        };
      }
      if (!('speechSynthesis' in window)) {
        finish(true);
        return () => {};
      }
      const synth = window.speechSynthesis;
      let utterance: SpeechSynthesisUtterance | null = null;
      let disposed = false;
      let timer: ReturnType<typeof setTimeout>;
      const start = () => {
        if (disposed || utterance) return;
        const voices = synth.getVoices().filter((voice) => voice.localService);
        if (!voices.length) return;
        const language = String(metadata.language || '');
        const selected = String(metadata.voice || '');
        const voice =
          voices.find((item) => item.voiceURI === selected || item.name === selected) ||
          voices.find(
            (item) => language && item.lang.toLowerCase().startsWith(language.toLowerCase())
          ) ||
          voices.find((item) => item.default) ||
          voices[0];
        utterance = new SpeechSynthesisUtterance(String(metadata.text || ''));
        utterance.voice = voice;
        utterance.lang = language || voice.lang;
        utterance.rate = Number(metadata.speed ?? 1);
        utterance.pitch = Number(metadata.pitch ?? 1);
        utterance.volume = Number(metadata.volume ?? 1);
        utterance.onstart = () => clearTimeout(timer);
        utterance.onend = () => finish();
        utterance.onerror = () => finish(true);
        synth.speak(utterance);
      };
      timer = setTimeout(() => finish(true), 8000);
      synth.addEventListener('voiceschanged', start);
      try {
        start();
      } catch {
        finish(true);
      }
      return () => {
        disposed = true;
        clearTimeout(timer);
        synth.removeEventListener('voiceschanged', start);
        if (utterance) {
          utterance.onstart = null;
          utterance.onend = null;
          utterance.onerror = null;
          synth.cancel();
        }
      };
    },
  };
}
