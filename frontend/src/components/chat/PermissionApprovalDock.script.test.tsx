import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { I18nProvider } from '../../i18n';
import type { AGUIPart } from '../../types/agui';
import { PermissionApprovalDock } from './PermissionApprovalDock';

const siteRule = (destination: 'session' | 'global') => [
  {
    type: 'add_rule' as const,
    destination,
    payload: {
      tool: 'browser_action',
      behavior: 'allow',
      matcher: { type: 'exact_input', value: { command: 'run_js', site: 'https://shop.example' } },
    },
  },
];

describe('browser code approval', () => {
  it('shows the code, its site and a choice per site', () => {
    const part = {
      type: 'tool',
      toolCallId: 'call-1',
      toolName: 'browser_action',
      args: JSON.stringify({
        command: 'run_js',
        arguments: ['return document.title'],
        site: 'https://shop.example',
      }),
      state: 'approval-requested',
      approvalId: 'approval-1',
      permission: {
        behavior: 'ask',
        reason: 'This tool can change external or persistent state',
        reasonCode: 'tool_requires_approval',
        risk: 'medium',
        actions: [
          { id: 'allow_once', label: 'Allow', behavior: 'allow', scope: 'once' },
          {
            id: 'allow_global',
            label: 'Always allow scripts on shop.example',
            behavior: 'allow',
            scope: 'global',
            permissionUpdates: siteRule('global'),
          },
          { id: 'reject', label: 'Reject', behavior: 'deny', scope: 'once' },
        ],
      },
    } as unknown as AGUIPart;
    const html = renderToStaticMarkup(
      <I18nProvider>
        <PermissionApprovalDock parts={[part]} onDecision={() => undefined} />
      </I18nProvider>
    );
    expect(html).toContain('May I run code on shop.example?');
    expect(html).toContain('return document.title');
    expect(html).toContain('with your sign-in there');
    expect(html).not.toContain('persistent state');
  });
});
