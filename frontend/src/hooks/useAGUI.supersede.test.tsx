import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAGUI } from './useAGUI';

type Frame = Record<string, unknown>;

/** A /chat/live body the test feeds by hand, ignoring the abort signal like a buffered read. */
function openStream() {
  let push!: (frame: Frame) => void;
  let close!: () => void;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      push = (frame) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(frame)}\n\n`));
      close = () => {
        // Cancelled already when the hook let go of the stream.
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };
    },
  });
  return { response: new Response(body), push: (f: Frame) => push(f), close: () => close() };
}

const snapshot = (run_id: string, delta: string) => ({
  type: 'STREAM_SNAPSHOT',
  run_id,
  seq: 1,
  events: [
    { type: 'TEXT_MESSAGE_START', messageId: run_id },
    { type: 'TEXT_MESSAGE_CONTENT', messageId: run_id, delta },
  ],
});
const content = (run_id: string, seq: number, delta: string) => ({
  type: 'STREAM_EVENT',
  run_id,
  seq,
  event: { type: 'TEXT_MESSAGE_CONTENT', messageId: run_id, delta },
});

const flush = () => new Promise((resolve) => setTimeout(resolve, 20));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useAGUI with a second stream', () => {
  it('stops folding the first stream into the buffer the second one owns', async () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(cb, 0));
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
    const chatA = openStream();
    const chatB = openStream();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(chatA.response).mockResolvedValueOnce(chatB.response)
    );
    const onFinish = vi.fn();
    let hook: ReturnType<typeof useAGUI> | null = null;
    const Probe: React.FC = () => {
      hook = useAGUI({ url: '/chat', onFinish });
      return null;
    };
    renderToStaticMarkup(<Probe />);
    const agui = hook!;

    const first = agui.sendMessage({ chat_id: 'A' }, { urlOverride: '/chat/live' });
    chatA.push(snapshot('run-a', 'from A'));
    await flush();
    expect(JSON.stringify(agui.getParts())).toContain('from A');

    const second = agui.sendMessage({ chat_id: 'B' }, { urlOverride: '/chat/live' });
    chatB.push(snapshot('run-b', 'from B'));
    await flush();
    // Frames chat A had already delivered when it was replaced.
    chatA.push(content('run-a', 2, ' leaked'));
    await flush();

    const parts = JSON.stringify(agui.getParts());
    expect(parts).toContain('from B');
    expect(parts).not.toContain('from A');
    expect(parts).not.toContain('leaked');
    await expect(first).resolves.toBe(false);
    expect(onFinish).not.toHaveBeenCalled();

    chatB.push({ type: 'STREAM_END', run_id: 'run-b', seq: 1, persisted: true });
    await expect(second).resolves.toBe(true);
    expect(onFinish).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(onFinish.mock.calls[0][0])).not.toContain('leaked');
    chatA.close();
  });

  it('lets a silent stop with nothing running leave the next stop audible', async () => {
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => setTimeout(cb, 0));
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
    const chat = openStream();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(chat.response));
    const onFinish = vi.fn();
    let hook: ReturnType<typeof useAGUI> | null = null;
    const Probe: React.FC = () => {
      hook = useAGUI({ url: '/chat', onFinish });
      return null;
    };
    renderToStaticMarkup(<Probe />);
    const agui = hook!;

    agui.stopSilently();
    const run = agui.sendMessage({ chat_id: 'A' }, { urlOverride: '/chat/live' });
    chat.push(snapshot('run-a', 'hello'));
    await flush();
    agui.stop();
    chat.push(content('run-a', 2, '!'));
    await run;

    expect(onFinish).toHaveBeenCalledTimes(1);
    chat.close();
  });
});
