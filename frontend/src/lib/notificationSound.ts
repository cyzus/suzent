/**
 * Notification sounds.
 *
 * Short tonal cues (`chime`, `ping`, `bell`, `success`) are synthesized with a
 * few Web Audio oscillators, while `resonance` plays a voiced "Suzent. <state>"
 * clip from `/sounds/resonance/<locale>/<cue>.mp3`, decoded into a cached
 * AudioBuffer, so the sound itself tells done, approval, failure and work apart.
 * Works in the desktop shell and in a plain browser.
 */
import { getInitialLocale } from '../i18n';
import type { NotificationSound } from './notificationPreferences';

/** What a notification is announcing; only `resonance` voices it. */
export type NotificationCue = 'ready' | 'approval' | 'failed' | 'working';

interface Note {
  /** Frequency in Hz. */
  freq: number;
  /** Offset from the cue start, in seconds. */
  start: number;
  /** Envelope length in seconds. */
  duration: number;
  type?: OscillatorType;
  gain?: number;
}

const PEAK_GAIN = 0.16;

type SynthesizedSound = 'chime' | 'ping' | 'bell' | 'success';

const SOUNDS: Record<SynthesizedSound, Note[]> = {
  chime: [
    { freq: 659.25, start: 0, duration: 0.45 }, // E5
    { freq: 783.99, start: 0.12, duration: 0.45 }, // G5
  ],
  ping: [{ freq: 1567.98, start: 0, duration: 0.25, type: 'sine', gain: 0.12 }], // G6
  bell: [
    { freq: 880, start: 0, duration: 0.6, type: 'triangle' }, // A5
    { freq: 1318.5, start: 0, duration: 0.5, type: 'sine', gain: 0.08 }, // E6
  ],
  success: [
    { freq: 523.25, start: 0, duration: 0.3 }, // C5
    { freq: 659.25, start: 0.1, duration: 0.3 }, // E5
    { freq: 783.99, start: 0.2, duration: 0.3 }, // G5
    { freq: 1046.5, start: 0.3, duration: 0.4 }, // C6
  ],
};

function resonanceSampleUrl(cue: NotificationCue): string {
  return `/sounds/resonance/${getInitialLocale()}/${cue}.mp3?v=1`;
}

let context: AudioContext | null = null;
const bufferCache = new Map<string, Promise<AudioBuffer | null>>();
let stopActiveSample: (() => void) | null = null;
let playbackGeneration = 0;

function ensureContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  try {
    const Ctor: typeof AudioContext | undefined =
      window.AudioContext ??
      // Safari still exposes the prefixed constructor.
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    if (!context || context.state === 'closed') context = new Ctor();
    return context;
  } catch {
    return null;
  }
}

/**
 * Browsers and desktop webviews refuse to start an AudioContext until the
 * page has seen a user gesture, so a task that finishes in a fresh window is
 * silent. Resuming the context inside the first pointer/key event unlocks it
 * for every later cue.
 */
let unlockBound = false;

function unlockAudio(): void {
  try {
    const ctx = ensureContext();
    if (ctx && ctx.state !== 'running') void ctx.resume().catch(() => {});
  } catch {
    /* ignore */
  }
}

function bindUnlock(): void {
  if (unlockBound || typeof window === 'undefined') return;
  unlockBound = true;
  // WebKit may interrupt audio again after the window loses focus. Keep
  // retrying within user gestures, including click (pointerdown is not
  // consistently treated as audio activation by WebKit).
  window.addEventListener('click', unlockAudio);
  window.addEventListener('keydown', unlockAudio);
}

bindUnlock();

function loadSampleBuffer(ctx: AudioContext, url: string): Promise<AudioBuffer | null> {
  const existing = bufferCache.get(url);
  if (existing) return existing;
  const pending = (async () => {
    try {
      if (typeof fetch !== 'function' || typeof ctx.decodeAudioData !== 'function') return null;
      const res = await fetch(url);
      if (!res.ok) return null;
      const bytes = await res.arrayBuffer();
      return await ctx.decodeAudioData(bytes);
    } catch {
      bufferCache.delete(url);
      return null;
    }
  })();
  bufferCache.set(url, pending);
  return pending;
}

function playSampledSound(url: string, generation: number): void {
  try {
    if (stopActiveSample) {
      stopActiveSample();
      stopActiveSample = null;
    }
    const ctx = ensureContext();
    if (ctx && typeof ctx.createBufferSource === 'function' && typeof fetch === 'function') {
      const ready = ctx.state === 'running' ? Promise.resolve() : ctx.resume();
      void ready
        .then(() => loadSampleBuffer(ctx, url))
        .then((buffer) => {
          if (generation !== playbackGeneration) return;
          try {
            if (buffer) {
              if (stopActiveSample) {
                stopActiveSample();
                stopActiveSample = null;
              }
              const source = ctx.createBufferSource();
              source.buffer = buffer;
              source.connect(ctx.destination);
              stopActiveSample = () => {
                try {
                  source.stop();
                  source.disconnect();
                } catch {
                  /* ignore */
                }
              };
              source.start(0);
              return;
            }
            if (typeof Audio !== 'undefined') {
              const audio = new Audio(url);
              stopActiveSample = () => {
                try {
                  audio.pause();
                } catch {
                  /* ignore */
                }
              };
              void audio.play().catch(() => {});
            }
          } catch {
            /* ignore */
          }
        })
        .catch(() => {});
      return;
    }
    if (typeof Audio !== 'undefined') {
      const audio = new Audio(url);
      stopActiveSample = () => {
        try {
          audio.pause();
        } catch {
          /* ignore */
        }
      };
      void audio.play().catch(() => {});
    }
  } catch {
    /* ignore */
  }
}

function scheduleNote(ctx: AudioContext, note: Note, now: number): void {
  const startAt = now + note.start;
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();

  oscillator.type = note.type ?? 'sine';
  oscillator.frequency.setValueAtTime(note.freq, startAt);

  // Attack instantly, decay smoothly, so it reads as a cue rather than a tone.
  const peak = note.gain ?? PEAK_GAIN;
  gain.gain.setValueAtTime(0.0001, startAt);
  gain.gain.exponentialRampToValueAtTime(peak, startAt + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + note.duration);

  oscillator.connect(gain);
  gain.connect(ctx.destination);
  oscillator.start(startAt);
  oscillator.stop(startAt + note.duration + 0.02);
}

function isSynthesizedSound(sound: Exclude<NotificationSound, 'none'>): sound is SynthesizedSound {
  return sound in SOUNDS;
}

/** Play a notification sound; `none` and any failure are silent no-ops. */
export function playNotificationSound(
  sound: NotificationSound,
  cue: NotificationCue = 'ready'
): void {
  const generation = ++playbackGeneration;
  if (sound === 'none') {
    if (stopActiveSample) {
      stopActiveSample();
      stopActiveSample = null;
    }
    return;
  }
  if (!isSynthesizedSound(sound)) {
    playSampledSound(resonanceSampleUrl(cue), generation);
    return;
  }
  try {
    if (stopActiveSample) {
      stopActiveSample();
      stopActiveSample = null;
    }
    const ctx = ensureContext();
    if (!ctx) return;
    const play = (): void => {
      if (generation !== playbackGeneration) return;
      const now = ctx.currentTime;
      for (const note of SOUNDS[sound]) scheduleNote(ctx, note, now);
    };
    if (ctx.state === 'running') play();
    else
      void ctx
        .resume()
        .then(play)
        .catch(() => {});
  } catch {
    // No audio device, a context that cannot resume, or a note that fails
    // mid-schedule: a notification cue must never interrupt the work that
    // fired it (the cron refresh and reply completion run here).
  }
}
