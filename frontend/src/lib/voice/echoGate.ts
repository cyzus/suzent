/**
 * Keeps Suzent's own voice, leaking from the speakers into the mic, from
 * reaching the provider's VAD (which would cut the reply off and transcribe
 * the echo as the user).
 *
 * While Suzent is audible (plus a short tail for output latency and room
 * reverb), mic frames are replaced with silence unless they are clearly louder
 * than the echo heard so far, for long enough to be speech. The frames held
 * while deciding are then released as-is, so the provider still hears the
 * start of the user's words. Outside playback every frame passes untouched.
 */

/** Loudness of one frame in dBFS, floored at -100 (NaN-safe). */
export function frameDb(frame: Float32Array): number {
  if (!frame.length) return -100;
  let sum = 0;
  for (let i = 0; i < frame.length; i += 1) sum += frame[i] * frame[i];
  const rms = Math.sqrt(sum / frame.length);
  // `!(rms > 0)` also catches NaN; a non-finite sample is garbage, not loud.
  if (!(rms > 0) || !Number.isFinite(rms)) return -100;
  return Math.max(-100, 20 * Math.log10(rms));
}

export interface EchoGateOptions {
  /** Never open below this, whatever the echo estimate. */
  minDb: number;
  /** How far above the echo estimate the user must be. */
  marginDb: number;
  /** How long the user must stay loud before the gate opens. */
  holdMs: number;
  /** How long below threshold before an open gate closes again. */
  releaseMs: number;
  /** How long after playback stops the echo is still expected. */
  tailMs: number;
  /** How fast the echo estimate falls back, in dB per second. */
  decayDbPerSecond: number;
  /**
   * Open this long with Suzent still playing means the provider did not take
   * it as an interruption: it was echo after all. Learn its level and close.
   */
  falseOpenMs: number;
  /**
   * Highest echo level the gate will learn. With the margin this caps the bar
   * at -18 dBFS, which a raised voice clears; beyond that the echo is too loud
   * to separate from the user without headphones.
   */
  maxEchoDb: number;
}

export const DEFAULT_ECHO_GATE: EchoGateOptions = {
  minDb: -38,
  marginDb: 12,
  holdMs: 200,
  releaseMs: 700,
  tailMs: 400,
  decayDbPerSecond: 6,
  falseOpenMs: 1500,
  maxEchoDb: -30,
};

const ECHO_FLOOR_START = -60;

export interface EchoGateStats {
  /** Frames replaced with silence because they looked like echo. */
  suppressed: number;
  /** Times a loud enough sound got through during playback (barge-in). */
  opened: number;
  /** Openings that turned out to be echo (see `falseOpenMs`). */
  falseOpens: number;
}

export class EchoGate {
  readonly options: EchoGateOptions;
  readonly stats: EchoGateStats = { suppressed: 0, opened: 0, falseOpens: 0 };
  private lastAudibleAt = -Infinity;
  private echoDb = ECHO_FLOOR_START;
  private open = false;
  private loudMs = 0;
  private quietMs = 0;
  private openMs = 0;
  private openDbSum = 0;
  private openFrames = 0;
  private held: Float32Array[] = [];

  constructor(options: Partial<EchoGateOptions> = {}) {
    this.options = { ...DEFAULT_ECHO_GATE, ...options };
  }

  /**
   * One mic frame in, the frames to send out (possibly none while deciding,
   * possibly several when held frames are released).
   */
  process(frame: Float32Array, frameMs: number, audible: boolean, nowMs: number): Float32Array[] {
    if (audible) this.lastAudibleAt = nowMs;
    if (nowMs - this.lastAudibleAt > this.options.tailMs) {
      // Suzent is silent: pass everything.
      const out = [...this.held, frame];
      this.reset();
      return out;
    }
    const db = frameDb(frame);
    const threshold = Math.max(this.options.minDb, this.echoDb + this.options.marginDb);
    const loud = db >= threshold;

    if (this.open) {
      // Only time with Suzent actually playing counts: once playback stopped
      // (the provider took it as a barge-in), what follows is the user.
      if (audible) {
        this.openMs += frameMs;
        if (loud) {
          this.openDbSum += db;
          this.openFrames += 1;
        }
      }
      if (audible && this.openMs >= this.options.falseOpenMs && this.openFrames) {
        // Still playing: the provider never heard an interruption in it.
        this.stats.falseOpens += 1;
        // Capped, so one misjudged opening cannot lock the user out.
        this.echoDb = Math.min(
          this.options.maxEchoDb,
          Math.max(this.echoDb, this.openDbSum / this.openFrames)
        );
        this.closeGate();
        this.stats.suppressed += 1;
        return [new Float32Array(frame.length)];
      }
      this.quietMs = loud ? 0 : this.quietMs + frameMs;
      if (this.quietMs >= this.options.releaseMs) this.closeGate();
      return [frame];
    }

    if (loud) {
      this.held.push(frame);
      this.loudMs += frameMs;
      if (this.loudMs >= this.options.holdMs) {
        this.open = true;
        this.stats.opened += 1;
        this.loudMs = 0;
        this.quietMs = 0;
        this.openMs = 0;
        this.openDbSum = 0;
        this.openFrames = 0;
        const out = this.held;
        this.held = [];
        return out;
      }
      return [];
    }

    // Quiet enough to be echo: learn from it, and drop what was held.
    this.echoDb = Math.min(
      this.options.maxEchoDb,
      Math.max(db, this.echoDb - (this.options.decayDbPerSecond * frameMs) / 1000)
    );
    const out = [...this.held, frame].map((f) => {
      this.stats.suppressed += 1;
      return new Float32Array(f.length);
    });
    this.held = [];
    this.loudMs = 0;
    return out;
  }

  /** Current dB a sound must reach during playback to get through. */
  threshold(): number {
    return Math.max(this.options.minDb, this.echoDb + this.options.marginDb);
  }

  private closeGate(): void {
    this.open = false;
    this.loudMs = 0;
    this.quietMs = 0;
    this.openMs = 0;
    this.openDbSum = 0;
    this.openFrames = 0;
  }

  /** The learned echo level is kept: same room, same volume, same call. */
  private reset(): void {
    this.closeGate();
    this.held = [];
  }
}
