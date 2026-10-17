import { describe, expect, it, vi } from 'vitest';
import { parseModelWait, requestModelWaitExtension } from './modelWait';

describe('model waiting', () => {
  it('clears inactive or malformed notices', () => {
    for (const value of [
      null,
      {},
      { active: false },
      { active: true, stage: 'slow' },
      { active: true, stage: 'unknown', wait_id: 'w' },
    ])
      expect(parseModelWait(value)).toBeNull();
    expect(parseModelWait({ active: true, stage: 'slow', wait_id: 'w', can_extend: true })).toEqual(
      { stage: 'slow', waitId: 'w', canExtend: true }
    );
    expect(
      parseModelWait({ active: true, stage: 'extended', wait_id: 'w', can_extend: false })
        ?.canExtend
    ).toBe(false);
  });
  it('names both the active run and the silent wait when extending', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    expect(await requestModelWaitExtension('/api', 'chat', 'run', 'wait', fetcher)).toBe(true);
    expect(fetcher).toHaveBeenCalledWith(
      '/api/chat/extend-wait',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ chat_id: 'chat', run_id: 'run', wait_id: 'wait' }),
      })
    );
  });
  it('does not present failed or stale extensions as accepted', async () => {
    const stale = vi.fn().mockResolvedValue(new Response('{}', { status: 409 }));
    const offline = vi.fn().mockRejectedValue(new Error('offline'));
    expect(await requestModelWaitExtension('', 'c', 'r', 'w', stale)).toBe(false);
    expect(await requestModelWaitExtension('', 'c', 'r', 'w', offline)).toBe(false);
  });
});
