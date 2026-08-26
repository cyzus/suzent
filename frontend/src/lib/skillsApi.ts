/**
 * Skills API client functions
 */

import { getApiBase } from './api';
import { Skill } from '../types/skills';

function scopeQuery(chatId?: string | null): string {
  return chatId ? `?chat_id=${encodeURIComponent(chatId)}` : '';
}

export async function fetchSkills(chatId?: string | null): Promise<Skill[]> {
  const res = await fetch(`${getApiBase()}/skills${scopeQuery(chatId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch skills: ${res.statusText}`);
  }
  return await res.json();
}

export async function reloadSkills(chatId?: string | null): Promise<Skill[]> {
  const res = await fetch(`${getApiBase()}/skills/reload${scopeQuery(chatId)}`, {
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`Failed to reload skills: ${res.statusText}`);
  }
  return await res.json();
}

export async function toggleSkill(
  skillId: string,
  enabled: boolean,
  chatId?: string | null
): Promise<void> {
  const res = await fetch(`${getApiBase()}/skills/toggle${scopeQuery(chatId)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ id: skillId, enabled }),
  });
  if (!res.ok) {
    throw new Error(`Failed to toggle skill: ${res.statusText}`);
  }
  // No return value expected for void promise, but consume body if any
  await res.text();
}
