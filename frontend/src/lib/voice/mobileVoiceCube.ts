import { mountVoiceCube, type VoiceCubeState } from './voiceCubeRenderer';

let state: VoiceCubeState = { status: 'connecting', working: false };
const micLevel = { current: 0 };
Object.assign(window, {
  updateVoiceCube(next: VoiceCubeState & { level?: number; dark?: boolean }) {
    micLevel.current = Math.max(0, Math.min(1, next.level ?? 0));
    state = { ...next, micLevel };
    document.documentElement.classList.toggle('dark', Boolean(next.dark));
  },
});
const canvas = document.querySelector<HTMLCanvasElement>('canvas');
if (canvas) {
  const stop = mountVoiceCube(canvas, () => state);
  window.addEventListener('pagehide', () => stop?.(), { once: true });
}
