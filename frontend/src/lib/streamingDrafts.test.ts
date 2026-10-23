import { describe, expect, it } from 'vitest';
import type { Message } from '../types/api';
import type { AGUIPart } from '../types/agui';
import { hideLiveTriggerRows, hideStreamingDrafts, splitLeadingTriggers } from './streamingDrafts';

describe('splitLeadingTriggers', () => {
  const trigger: AGUIPart = { type: 'incoming-message', text: 'Run the task', persisted: true };
  const reply: AGUIPart = { type: 'text', text: 'Working on it' };

  it('places the opening trigger before the assistant response', () => {
    expect(splitLeadingTriggers([trigger, reply])).toEqual({
      triggers: [trigger],
      response: [reply],
    });
  });

  it('shows the trigger even before any response arrives', () => {
    expect(splitLeadingTriggers([trigger])).toEqual({ triggers: [trigger], response: [] });
    expect(splitLeadingTriggers([])).toEqual({ triggers: [], response: [] });
  });

  it('keeps mid-turn messages in their original timeline position', () => {
    const incoming: AGUIPart = { type: 'incoming-message', text: 'One more thing' };
    expect(splitLeadingTriggers([trigger, reply, incoming, trigger])).toEqual({
      triggers: [trigger],
      response: [reply, incoming, trigger],
    });
    expect(splitLeadingTriggers([incoming, reply])).toEqual({
      triggers: [],
      response: [incoming, reply],
    });
  });
});

describe('hideStreamingDrafts', () => {
  it('hides backend streaming drafts while a transient stream is shown', () => {
    const user: Message = { role: 'user', content: 'run it' };
    const draft: Message = {
      role: 'assistant',
      content: '',
      _streaming_draft: true,
      parts: [{ type: 'tool', toolCallId: 'call-1', toolName: 'run_command', state: 'running' }],
    };
    const final: Message = { role: 'assistant', content: 'done' };

    expect(hideStreamingDrafts([user, draft, final], true)).toEqual([user, final]);
  });

  it('keeps drafts when no transient stream is visible', () => {
    const draft: Message = {
      role: 'assistant',
      content: '',
      _streaming_draft: true,
      parts: [{ type: 'reasoning', text: 'still working' }],
    };

    expect(hideStreamingDrafts([draft], false)).toEqual([draft]);
  });
});

describe('hideLiveTriggerRows', () => {
  const trigger = '[Agent message from Laptop (device:abc)]\nCheck the build';
  const live: AGUIPart[] = [{ type: 'incoming-message', text: trigger, persisted: true }];

  it('hides the stored row the live run is already showing', () => {
    const row: Message = { role: 'system_triggered', content: trigger };
    const user: Message = { role: 'user', content: 'hi' };

    expect(hideLiveTriggerRows([user, row], live)).toEqual([user]);
  });

  it('keeps an earlier turn with the same trigger', () => {
    const earlier: Message = { role: 'system_triggered', content: trigger };
    const reply: Message = { role: 'assistant', content: 'done' };
    const current: Message = { role: 'system_triggered', content: trigger };

    expect(hideLiveTriggerRows([earlier, reply, current], live)).toEqual([earlier, reply]);
  });

  it('leaves rows alone for messages injected mid-turn', () => {
    const row: Message = { role: 'system_triggered', content: trigger };
    const injected: AGUIPart[] = [{ type: 'incoming-message', text: trigger }];

    expect(hideLiveTriggerRows([row], injected)).toEqual([row]);
  });
});

describe('settled streaming drafts', () => {
  const draft: Message = { role: 'assistant', content: 'done', _streaming_draft: true };
  const reply: Message = { role: 'assistant', content: 'done' };
  it('hides a stale draft duplicated by the settled reply in its turn', () => {
    expect(hideStreamingDrafts([draft, reply], false)).toEqual([reply]);
  });
  it('does not match identical replies across triggered turns', () => {
    const trigger: Message = { role: 'system_triggered', content: 'run again' };
    expect(hideStreamingDrafts([draft, trigger, reply], false)).toEqual([draft, trigger, reply]);
  });
  it('keeps an unmatched recovery draft', () => {
    const partial: Message = { role: 'assistant', content: 'partial' };
    expect(hideStreamingDrafts([draft, partial], false)).toEqual([draft, partial]);
  });
});
