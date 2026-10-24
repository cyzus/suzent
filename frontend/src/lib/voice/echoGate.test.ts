import { describe, expect, it } from 'vitest';
import { EchoGate, frameDb } from './echoGate';

const FRAME_MS = 30;
/** A 30ms frame (480 samples at 16kHz) at roughly `db` dBFS RMS. */
const tone = (db: number) => {
  const amplitude = Math.SQRT2 * 10 ** (db / 20);
  return Float32Array.from({ length: 480 }, (_, i) => amplitude * Math.sin(i / 3));
};
const isSilent = (frame: Float32Array) => frame.every((s) => s === 0);

/** Feed frames 30ms apart; returns everything the gate let out, in order. */
function run(gate: EchoGate, frames: Array<[Float32Array, boolean]>, start = 0) {
  const out: Float32Array[] = [];
  frames.forEach(([frame, audible], i) => {
    out.push(...gate.process(frame, FRAME_MS, audible, start + i * FRAME_MS));
  });
  return out;
}

describe('frameDb', () => {
  it('measures RMS loudness and is NaN-safe', () => {
    expect(frameDb(tone(-20))).toBeCloseTo(-20, 0);
    expect(frameDb(new Float32Array(480))).toBe(-100);
    expect(frameDb(new Float32Array(0))).toBe(-100);
    expect(frameDb(Float32Array.of(0.1, NaN))).toBe(-100);
  });
});

describe('EchoGate', () => {
  it('passes everything untouched while Suzent is silent', () => {
    const gate = new EchoGate();
    const frames = [tone(-50), tone(-20), tone(-45)];
    const out = run(
      gate,
      frames.map((f) => [f, false])
    );
    expect(out).toEqual(frames);
    expect(gate.stats.suppressed).toBe(0);
  });

  it('turns echo into silence while Suzent speaks, keeping the frame count', () => {
    const gate = new EchoGate();
    const out = run(
      gate,
      Array.from({ length: 50 }, () => [tone(-45), true])
    );
    expect(out).toHaveLength(50);
    expect(out.every(isSilent)).toBe(true);
    expect(gate.stats.suppressed).toBe(50);
  });

  it('lets a loud barge-in through after the hold, including its onset', () => {
    const gate = new EchoGate();
    const echo = Array.from({ length: 10 }, (): [Float32Array, boolean] => [tone(-45), true]);
    const speech = Array.from({ length: 10 }, (): [Float32Array, boolean] => [tone(-15), true]);
    const out = run(gate, [...echo, ...speech]);
    // Echo silenced; every speech frame delivered as-is, held ones included.
    expect(out).toHaveLength(20);
    expect(out.slice(0, 10).every(isSilent)).toBe(true);
    expect(out.slice(10)).toEqual(speech.map(([f]) => f));
    expect(gate.stats.opened).toBe(1);
  });

  it('drops a short loud burst (a cough, a click) during playback', () => {
    const gate = new EchoGate();
    const out = run(gate, [
      [tone(-15), true],
      [tone(-15), true],
      [tone(-50), true],
    ]);
    expect(out).toHaveLength(3);
    expect(out.every(isSilent)).toBe(true);
    expect(gate.stats.opened).toBe(0);
  });

  it('raises the bar as it hears louder echo', () => {
    const loud30 = () =>
      Array.from({ length: 10 }, (): [Float32Array, boolean] => [tone(-30), true]);
    // A fresh gate (bar at -38) lets -30 dBFS through ...
    expect(run(new EchoGate(), loud30()).some(isSilent)).toBe(false);
    // ... but after hearing -40 dBFS echo the bar is ~-28, so -30 is echo.
    const gate = new EchoGate();
    run(
      gate,
      Array.from({ length: 20 }, () => [tone(-40), true])
    );
    expect(gate.threshold()).toBeGreaterThan(-30);
    expect(run(gate, loud30(), 20 * FRAME_MS).every(isSilent)).toBe(true);
  });

  it('learns echo that opened the gate when the provider never interrupted', () => {
    const gate = new EchoGate();
    // Loud echo (-28 dBFS) keeps playing: opens, then after falseOpenMs is learned.
    const out = run(
      gate,
      Array.from({ length: 80 }, () => [tone(-28), true])
    );
    expect(gate.stats.opened).toBe(1);
    expect(gate.stats.falseOpens).toBe(1);
    expect(isSilent(out[out.length - 1])).toBe(true);
    // The user, clearly louder than that echo, still gets through.
    const after = run(
      gate,
      Array.from({ length: 10 }, () => [tone(-10), true]),
      80 * FRAME_MS
    );
    expect(after.some((f) => !isSilent(f))).toBe(true);
  });

  it('does not learn a real barge-in as echo once playback has stopped', () => {
    const gate = new EchoGate();
    // User interrupts at -20 dBFS; Gemini takes 1.2s to stop playback.
    const during = run(
      gate,
      Array.from({ length: 47 }, (): [Float32Array, boolean] => [tone(-20), true])
    );
    // Playback flushed; the user keeps talking through the 400ms tail.
    const tail = run(
      gate,
      Array.from({ length: 13 }, (): [Float32Array, boolean] => [tone(-20), false]),
      47 * FRAME_MS
    );
    expect(gate.stats.falseOpens).toBe(0);
    expect([...during.slice(7), ...tail].some(isSilent)).toBe(false);
    // Next reply: the user can still barge in at a normal level.
    const next = run(
      gate,
      Array.from({ length: 20 }, (): [Float32Array, boolean] => [tone(-25), true]),
      5000
    );
    expect(next.some((f) => !isSilent(f))).toBe(true);
  });

  it('caps what it learns, so a raised voice always gets through', () => {
    const gate = new EchoGate();
    // Very loud "echo" that keeps playing: learned, but capped at -30.
    run(
      gate,
      Array.from({ length: 200 }, () => [tone(-8), true])
    );
    expect(gate.threshold()).toBeLessThanOrEqual(-18);
    const shout = run(
      gate,
      Array.from({ length: 10 }, (): [Float32Array, boolean] => [tone(-12), true]),
      200 * FRAME_MS
    );
    expect(shout.some((f) => !isSilent(f))).toBe(true);
  });

  it('treats non-finite samples as silence, not as infinitely loud echo', () => {
    expect(frameDb(Float32Array.of(Infinity, 0))).toBe(-100);
    const gate = new EchoGate();
    run(gate, [[Float32Array.of(Infinity, 0.1), true]]);
    expect(Number.isFinite(gate.threshold())).toBe(true);
  });

  it('closes again after the user goes quiet, and reopens on silence after the tail', () => {
    const gate = new EchoGate();
    run(
      gate,
      Array.from({ length: 10 }, () => [tone(-15), true])
    );
    expect(gate.stats.opened).toBe(1);
    // 700ms of quiet closes it: further echo is silenced again.
    const quiet = run(
      gate,
      Array.from({ length: 30 }, () => [tone(-50), true]),
      300
    );
    expect(isSilent(quiet[quiet.length - 1])).toBe(true);
    // Playback ended more than tailMs ago: everything passes.
    const frame = tone(-50);
    expect(gate.process(frame, FRAME_MS, false, 300 + 30 * FRAME_MS + 500)).toEqual([frame]);
  });

  it('releases held frames untouched when playback ends mid-decision', () => {
    const gate = new EchoGate();
    const a = tone(-15);
    const b = tone(-15);
    expect(gate.process(a, FRAME_MS, true, 0)).toEqual([]);
    // Suzent stopped long enough ago: held onset and the new frame both pass.
    expect(gate.process(b, FRAME_MS, false, 1000)).toEqual([a, b]);
  });
});
