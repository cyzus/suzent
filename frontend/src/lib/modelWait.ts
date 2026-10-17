export interface ModelWaitState {
  stage: 'waiting' | 'slow' | 'extended';
  waitId: string;
  canExtend: boolean;
}

export function parseModelWait(value: unknown): ModelWaitState | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (data.active !== true || typeof data.wait_id !== 'string' || !data.wait_id) return null;
  if (data.stage !== 'waiting' && data.stage !== 'slow' && data.stage !== 'extended') return null;
  return { stage: data.stage, waitId: data.wait_id, canExtend: data.can_extend === true };
}

export async function requestModelWaitExtension(
  baseUrl: string,
  chatId: string,
  runId: string,
  waitId: string,
  fetcher: typeof fetch = fetch
): Promise<boolean> {
  try {
    const response = await fetcher(`${baseUrl}/chat/extend-wait`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, run_id: runId, wait_id: waitId }),
    });
    return response.ok;
  } catch {
    return false;
  }
}
