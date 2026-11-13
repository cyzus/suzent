import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import { buildTriggerPlan, isSilentReply, parseTrigger, triggerPreview } from './triggerRows';

const agentTrigger = (sender: string, body: string, id = 'ea0f'): Message => ({
  role: 'system_triggered',
  content: `[Agent message from ${sender} (${id})]\n<!-- suzent-agent-inbox:x -->\n${body}`,
});
const cron = (name: string): Message => ({
  role: 'system_triggered',
  content: `**Scheduled Task: ${name}**\n\nDo it`,
});
const reply = (content: string): Message => ({ role: 'assistant', content });
const quiet = (): Message => ({
  role: 'assistant',
  content: '',
  parts: [
    { type: 'reasoning', text: 'thinking' },
    { type: 'text', text: 'HEARTBEAT_OK' },
  ],
});

describe('parseTrigger', () => {
  it('reads an agent message header and drops the inbox marker', () => {
    const trigger = parseTrigger(agentTrigger('Release check 每日', '## Report\nAll good').content);
    expect(trigger).toMatchObject({
      kind: 'agent',
      source: 'Release check 每日',
      reference: 'ea0f',
      body: '## Report\nAll good',
      key: 'agent:ea0f',
    });
  });

  it('reads scheduled tasks, goal mode and other reminders', () => {
    expect(parseTrigger('**Scheduled Task: Stand-up**\n\nRemind')).toMatchObject({
      kind: 'scheduled',
      source: 'Stand-up',
      body: 'Remind',
    });
    expect(parseTrigger('[Goal mode] Keep going')).toMatchObject({
      kind: 'goal',
      body: 'Keep going',
    });
    expect(parseTrigger('**Sub-agent finished**\nResult')).toMatchObject({
      kind: 'other',
      source: 'Sub-agent finished',
      body: 'Result',
    });
  });
});

describe('triggerPreview', () => {
  it('returns the first meaningful line as plain text', () => {
    expect(triggerPreview('\n---\n- **v0.14.2** shipped [notes](https://x)\nmore')).toBe(
      'v0.14.2 shipped notes'
    );
    expect(triggerPreview('## Daily report\nAll green')).toBe('All green');
    expect(triggerPreview('## Daily report')).toBe('Daily report');
  });
});

describe('isSilentReply', () => {
  it('treats reasoning plus a quiet token as silent, and real text as not', () => {
    expect(isSilentReply(quiet())).toBe(true);
    expect(isSilentReply(reply('HEARTBEAT_OK'))).toBe(true);
    expect(isSilentReply(reply('Here is what changed'))).toBe(false);
    expect(
      isSilentReply({ role: 'assistant', content: '', parts: [{ type: 'tool-call' } as never] })
    ).toBe(false);
  });
});

describe('buildTriggerPlan', () => {
  it('merges repeats of the same trigger that got no reply', () => {
    const rows = [cron('Check'), quiet(), cron('Check'), quiet(), cron('Check'), quiet()];
    const plan = buildTriggerPlan(rows, new Set());

    expect([...plan.rows.keys()]).toEqual([4]);
    expect(plan.rows.get(4)?.map((entry) => entry.state)).toEqual(['quiet', 'quiet', 'quiet']);
    expect([...plan.skipIndices].sort()).toEqual([0, 1, 2, 3, 5]);
    expect(plan.replies.size).toBe(0);
  });

  it('moves an answered trigger onto its reply', () => {
    const rows = [agentTrigger('A', 'one'), quiet(), agentTrigger('A', 'two'), reply('Done')];
    const plan = buildTriggerPlan(rows, new Set());

    expect(plan.rows.size).toBe(0);
    expect(plan.replies.get(3)?.map((entry) => entry.state)).toEqual(['quiet', 'replied']);
    expect([...plan.skipIndices].sort()).toEqual([0, 1, 2]);
  });

  it('keeps different senders apart', () => {
    const rows = [agentTrigger('A', 'one', 'a'), quiet(), agentTrigger('B', 'two', 'b'), quiet()];
    const plan = buildTriggerPlan(rows, new Set());

    expect([...plan.rows.keys()]).toEqual([0, 2]);
  });

  it('leaves a trigger before a live reply on its own row, still pending', () => {
    const rows = [cron('Check'), reply('')];
    const plan = buildTriggerPlan(rows, new Set(), 1);

    expect(plan.rows.get(0)?.[0].state).toBe('pending');
    expect(plan.replies.size).toBe(0);
    expect(plan.skipIndices.size).toBe(0);
  });

  it('leaves user rows and Regent-relayed requests alone', () => {
    const rows: Message[] = [
      { role: 'user', content: 'hi' },
      {
        role: 'system_triggered',
        content: '[Agent message from Regent (focal-suzent)]\nPlease check',
      },
      reply('ok'),
    ];
    const plan = buildTriggerPlan(rows, new Set());

    expect(plan.rows.size).toBe(0);
    expect(plan.replies.size).toBe(0);
  });
});
