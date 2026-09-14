import { describe, expect, it, vi } from 'vitest';
import { completeDirectStream } from './completeDirectStream';

describe('direct stream completion after navigation', () => {
  function fixture() {
    return {
      isSelected: vi.fn(() => true),
      ownsStream: vi.fn(() => true),
      loadHistory: vi.fn(async () => {}),
      clearChatStreaming: vi.fn(),
      clearTransient: vi.fn(),
      clearSeed: vi.fn(),
    };
  }

  it('does not select the old chat but still clears its streaming state and seed', async () => {
    const completion = fixture();
    completion.isSelected.mockReturnValue(false);
    await completeDirectStream(completion);
    expect(completion.loadHistory).not.toHaveBeenCalled();
    expect(completion.clearChatStreaming).toHaveBeenCalledOnce();
    expect(completion.clearTransient).toHaveBeenCalledOnce();
    expect(completion.clearSeed).toHaveBeenCalledOnce();
  });

  it('does not clear a newer stream started while history was loading', async () => {
    const completion = fixture();
    let release!: () => void;
    completion.loadHistory.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        })
    );
    const finished = completeDirectStream(completion);
    completion.isSelected.mockReturnValue(false);
    completion.ownsStream.mockReturnValue(false);
    release();
    await finished;
    expect(completion.clearChatStreaming).toHaveBeenCalledOnce();
    expect(completion.clearTransient).not.toHaveBeenCalled();
    expect(completion.clearSeed).toHaveBeenCalledOnce();
  });

  it('clears chat state but retains received parts for the error handler on load failure', async () => {
    const completion = fixture();
    completion.loadHistory.mockRejectedValue(new Error('offline'));
    await expect(completeDirectStream(completion)).rejects.toThrow('offline');
    expect(completion.clearChatStreaming).toHaveBeenCalledOnce();
    expect(completion.clearTransient).not.toHaveBeenCalled();
    expect(completion.clearSeed).toHaveBeenCalledOnce();
  });
});
