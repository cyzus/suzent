import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ToolPermissionDecision } from '../../types/agui';
import { I18nProvider, tForLocale } from '../../i18n';
import { shouldShowPolicyAllowedBadge, ToolCallBlock } from './ToolCallBlock';

function decision(overrides: Partial<ToolPermissionDecision> = {}): ToolPermissionDecision {
  return {
    toolCallId: 'call-1',
    toolName: 'run_command',
    behavior: 'allow',
    source: 'policy',
    reason: 'Allowed by deterministic shell policy',
    reasonCode: 'shell_policy_allow',
    risk: 'safe',
    riskCategories: [],
    ...overrides,
  };
}

describe('policy permission badge', () => {
  it('shows state-changing deterministic policy allows', () => {
    expect(shouldShowPolicyAllowedBadge(decision())).toBe(true);
  });

  it('suppresses routine read-only policy allows', () => {
    expect(
      shouldShowPolicyAllowedBadge(
        decision({
          reasonCode: 'readonly_operation',
        })
      )
    ).toBe(false);
  });
});

const autoAllowed = decision({
  behavior: 'allow',
  source: 'auto_classifier',
  reasonCode: 'auto_classifier_allow',
  confidence: 'high',
});

function renderAutoAllowed({ expanded }: { expanded: boolean }): string {
  return renderToStaticMarkup(
    React.createElement(
      I18nProvider,
      null,
      React.createElement(ToolCallBlock, {
        toolName: 'run_command',
        defaultCollapsed: !expanded,
        inActivityRail: true,
        permissionDecision: autoAllowed,
      })
    )
  );
}

// Matches the confidence wording in either locale, so this holds whichever
// language the provider resolves to.
const confidenceWording = /confidence|置信度/i;

describe('auto-allowed permission badge', () => {
  it('names the decision without restating the confidence level', () => {
    const html = renderAutoAllowed({ expanded: false });
    expect(html).toContain(tForLocale('en', 'toolCallBlock.permissionAutoAllowed'));
    expect(html).not.toMatch(confidenceWording);
  });

  it('still reports the confidence in the permission panel', () => {
    expect(renderAutoAllowed({ expanded: true })).toMatch(confidenceWording);
  });
});

describe('pending approval badge', () => {
  const askDecision = decision({
    behavior: 'ask',
    reason: 'Command requires approval',
    reasonCode: 'shell_chaining',
    risk: 'high',
  });
  const reviewRequired = tForLocale('en', 'toolCallBlock.permissionReviewRequired');

  function render(approvalState?: 'pending'): string {
    return renderToStaticMarkup(
      React.createElement(
        I18nProvider,
        null,
        React.createElement(ToolCallBlock, {
          toolName: 'run_command',
          toolArgs: JSON.stringify({ content: 'ls', description: 'List files' }),
          inActivityRail: true,
          approvalState,
          permissionDecision: askDecision,
        })
      )
    );
  }

  // The rail header and the approval dock already say a decision is pending,
  // so the row repeating it was the second badge users saw.
  it('leaves the review-required chip off a call still waiting on the user', () => {
    expect(render('pending')).not.toContain(reviewRequired);
  });

  it('keeps the chip on a call that is no longer actionable', () => {
    expect(render()).toContain(reviewRequired);
  });
});
