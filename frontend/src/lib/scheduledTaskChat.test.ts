import { describe, expect, it } from 'vitest';
import { getScheduledTaskChat } from './scheduledTaskChat';

describe('scheduled task conversations', () => {
  it.each([null, '2026-09-24T10:00:00Z'])(
    'opens the existing bound conversation before and after a run (%s)',
    (lastRunAt) => {
      expect(
        getScheduledTaskChat({
          id: 42,
          context_mode: 'bound',
          chat_id: 'original-chat',
          last_run_at: lastRunAt,
        })
      ).toEqual({ chatId: 'original-chat', canOpen: true, ownsChat: false });
    }
  );

  it('keeps an unrun isolated task in automation settings', () => {
    expect(
      getScheduledTaskChat({ id: 42, context_mode: 'isolated', chat_id: null, last_run_at: null })
    ).toEqual({ chatId: 'cron-42', canOpen: false, ownsChat: true });
  });

  it('opens the owned conversation of an isolated task after a run', () => {
    expect(
      getScheduledTaskChat({
        id: 42,
        context_mode: 'isolated',
        chat_id: 'unrelated-chat',
        last_run_at: '2026-09-24T10:00:00Z',
      })
    ).toEqual({ chatId: 'cron-42', canOpen: true, ownsChat: true });
  });

  it('matches the server fallback for a bound task without a chat ID', () => {
    expect(
      getScheduledTaskChat({ id: 42, context_mode: 'bound', chat_id: null, last_run_at: null })
    ).toEqual({ chatId: 'cron-42', canOpen: false, ownsChat: true });
  });
});
