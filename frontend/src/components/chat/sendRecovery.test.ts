import { describe, it, expect } from 'vitest';
import { planSendFailureRecovery, type SendAction } from './sendRecovery';
import { tForLocale } from '../../i18n';

describe('planSendFailureRecovery', () => {
  it('re-attaches instead of going idle when the chat is still responding', () => {
    const plan = planSendFailureRecovery(409, 'send');
    expect(plan.reattach).toBe(true);
    expect(plan.restoreInput).toBe(true);
    expect(plan.tone).toBe('info');
  });

  it('does not blame the user for a conflict that the backend created', () => {
    // The message has to read as "your turn is still running", not as a failure,
    // because the response the user is waiting for is about to render.
    const plan = planSendFailureRecovery(409, 'send');
    expect(tForLocale('en', plan.messageKey, plan.messageParams)).toMatch(/still responding/i);
  });

  it('tears the optimistic state down for a genuine failure', () => {
    for (const status of [400, 404, 422, 500, 503]) {
      const plan = planSendFailureRecovery(status, 'send');
      expect(plan.reattach).toBe(false);
      expect(plan.restoreInput).toBe(false);
      expect(plan.tone).toBe('error');
    }
  });

  it('names the rejected action and its status in the failure message', () => {
    const cases: Array<[SendAction, number, string]> = [
      ['retry', 500, 'Retry failed (500)'],
      ['edit', 404, 'Edit failed (404)'],
      ['steer', 503, 'Steer failed (503)'],
      ['send', 500, 'Send failed (500)'],
    ];
    for (const [action, status, expected] of cases) {
      const plan = planSendFailureRecovery(status, action);
      expect(tForLocale('en', plan.messageKey, plan.messageParams)).toBe(expected);
    }
  });

  it('resolves every message in each supported locale', () => {
    // A missing key falls back to returning the key itself, which would ship a
    // dotted identifier to the status bar.
    const actions: SendAction[] = ['send', 'steer', 'retry', 'edit'];
    for (const locale of ['en', 'zh-CN'] as const) {
      for (const status of [409, 500]) {
        for (const action of actions) {
          const plan = planSendFailureRecovery(status, action);
          const text = tForLocale(locale, plan.messageKey, plan.messageParams);
          expect(text).not.toBe(plan.messageKey);
          expect(text).not.toMatch(/\{status\}/);
        }
      }
    }
  });
});
