import { describe, it, expect } from 'vitest';
import { processEvent } from './useAGUI';

describe('processEvent RUN_ERROR', () => {
  it('treats a user stop as an expected ending, not an error', () => {
    // The backend tags the cancellation frame. Reading it as an error would
    // tear the stream down just before the STREAM_END that confirms the
    // stopped turn was persisted.
    const result = processEvent(
      { type: 'RUN_ERROR', data: { message: 'Stream stopped by user', code: 'stream_stopped' } },
      []
    );

    expect(result.error).toBeUndefined();
  });

  it('still reports a real run error', () => {
    const result = processEvent({ type: 'RUN_ERROR', data: { message: 'boom' } }, []);

    expect(result.error).toBe('boom');
  });

  it('keeps the failure code so a stalled model can get a localized hint', () => {
    const result = processEvent(
      { type: 'RUN_ERROR', data: { message: 'Request timed out.', code: 'model_stalled' } },
      []
    );

    expect(result.error).toBe('Request timed out.');
    expect(result.errorCode).toBe('model_stalled');
  });
});
