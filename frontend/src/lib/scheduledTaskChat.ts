import type { CronJob } from './api';

type ScheduledTaskChat = Pick<
  CronJob,
  'id' | 'context_mode' | 'chat_id' | 'last_run_at' | 'chat_updated_at'
>;

export function getScheduledTaskChat(job: ScheduledTaskChat): {
  chatId: string;
  canOpen: boolean;
  ownsChat: boolean;
} {
  const boundChatId = job.context_mode === 'bound' ? job.chat_id : null;
  return {
    chatId: boundChatId || `cron-${job.id}`,
    canOpen: Boolean(boundChatId ? job.chat_updated_at : job.last_run_at),
    ownsChat: !boundChatId,
  };
}
