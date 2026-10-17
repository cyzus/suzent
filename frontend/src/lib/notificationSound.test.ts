import { afterEach, expect, it, vi } from 'vitest';

afterEach(() => vi.unstubAllGlobals());

it.each(['suspended', 'interrupted'])('recovers %s audio before playing', async (initial) => {
  vi.resetModules();
  let state = initial;
  let finishResume!: () => void;
  const start = vi.fn();
  const resume = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finishResume = () => {
          state = 'running';
          resolve();
        };
      })
  );
  class MockAudioContext {
    get state(): string {
      return state;
    }
    currentTime = 10;
    destination = {};
    resume = resume;
    createOscillator = () => ({
      frequency: { setValueAtTime: vi.fn() },
      connect: vi.fn(),
      start,
      stop: vi.fn(),
    });
    createGain = () => ({
      gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
    });
  }
  const addEventListener = vi.fn();
  vi.stubGlobal('window', { AudioContext: MockAudioContext, addEventListener });
  const { playNotificationSound } = await import('./notificationSound');
  playNotificationSound('ping');
  expect(resume).toHaveBeenCalledOnce();
  expect(start).not.toHaveBeenCalled();
  finishResume();
  await Promise.resolve();
  expect(start).toHaveBeenCalledWith(10);
  expect(addEventListener).toHaveBeenCalledWith('click', expect.any(Function));
  expect(addEventListener).toHaveBeenCalledWith('keydown', expect.any(Function));
});

it.each([
  ['en', 'approval', '/sounds/resonance/en/approval.mp3?v=1'],
  ['zh-CN', 'failed', '/sounds/resonance/zh-CN/failed.mp3?v=1'],
  ['en', undefined, '/sounds/resonance/en/ready.mp3?v=1'],
] as const)('voices the %s resonance clip for the %s cue', async (locale, cue, url) => {
  vi.resetModules();
  const fetch = vi.fn(async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
  const start = vi.fn();
  class MockAudioContext {
    state = 'running';
    currentTime = 0;
    destination = {};
    resume = vi.fn(async () => {});
    decodeAudioData = vi.fn(async () => ({}));
    createBufferSource = () => ({ connect: vi.fn(), start, stop: vi.fn(), disconnect: vi.fn() });
  }
  vi.stubGlobal('window', { AudioContext: MockAudioContext, addEventListener: vi.fn() });
  vi.stubGlobal('fetch', fetch);
  vi.stubGlobal('localStorage', { getItem: () => locale, setItem: vi.fn() });
  const { playNotificationSound } = await import('./notificationSound');
  playNotificationSound('resonance', cue);
  await vi.waitFor(() => expect(start).toHaveBeenCalledWith(0));
  expect(fetch).toHaveBeenCalledWith(url);
});
