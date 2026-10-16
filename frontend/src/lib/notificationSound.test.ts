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
