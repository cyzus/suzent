import { describe, it, expect } from 'vitest';
import { planSendFailureRecovery } from './sendRecovery';

describe('planSendFailureRecovery', () => {
  it('re-attaches instead of going idle when the chat is still responding', () => {
    const plan = planSendFailureRecovery(409, 'Send');
    expect(plan.reattach).toBe(true);
    expect(plan.restoreInput).toBe(true);
    expect(plan.tone).toBe('info');
  });

  it('does not blame the user for a conflict that the backend created', () => {
    // The message has to read as "your turn is still running", not as a failure,
    // because the response the user is waiting for is about to render.
    expect(planSendFailureRecovery(409, 'Send').message).toMatch(/still responding/i);
  });

  it('tears the optimistic state down for a genuine failure', () => {
    for (const status of [400, 404, 422, 500, 503]) {
      const plan = planSendFailureRecovery(status, 'Send');
      expect(plan.reattach).toBe(false);
      expect(plan.restoreInput).toBe(false);
      expect(plan.tone).toBe('error');
    }
  });

  it('names the rejected action and its status in the failure message', () => {
    expect(planSendFailureRecovery(500, 'Retry').message).toBe('Retry failed (500)');
    expect(planSendFailureRecovery(404, 'Edit').message).toBe('Edit failed (404)');
    expect(planSendFailureRecovery(503, 'Steer').message).toBe('Steer failed (503)');
  });
});
