import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { ModelRolesTab } from './ModelRolesTab';

function renderRoles(roleModels: Record<string, string[]>): string {
  return renderToStaticMarkup(
    <I18nProvider>
      <ModelRolesTab
        roleModels={roleModels}
        suggestions={{}}
        unregisteredModels={[]}
        onChange={() => {}}
      />
    </I18nProvider>
  );
}

describe('Model role inheritance settings', () => {
  it('groups defaults, background tasks and specialists in order', () => {
    const html = renderRoles({ primary: ['main'] });
    expect(html.indexOf('Default models')).toBeLessThan(html.indexOf('Background tasks'));
    expect(html.indexOf('Background tasks')).toBeLessThan(html.indexOf('Specialist models'));
    expect(html).toContain('Inherited');
    expect(html).toContain('Not configured');
  });
  it('keeps individual decision overrides in the collapsed advanced section', () => {
    const html = renderRoles({ decision: ['decision-model'], cheap: ['lightweight'] });
    const advanced = html.slice(html.indexOf('<details'), html.indexOf('</details>'));
    expect(advanced).not.toContain('open=""');
    expect(advanced).toContain('Goal Judge');
    expect(advanced).toContain('Permission Review');
    expect(advanced).toContain('Inherited: decision-model');
    expect(advanced).not.toContain('Inherited: lightweight');
    expect(html).not.toContain('settings.roles.');
  });

  it('shows the nearest parent and respects explicit child assignments', () => {
    const html = renderRoles({ primary: ['main'], goal_judge: ['custom-judge'] });
    const advanced = html.slice(html.indexOf('<details'), html.indexOf('</details>'));
    expect(advanced).toContain('custom-judge');
    expect(advanced).toContain('1 overrides');
    expect(advanced).toContain('Use inherited models');
    expect(advanced.match(/Inherited: main/g)).toHaveLength(1);
  });
});
