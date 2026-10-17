import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it, vi } from 'vitest';
import { ModelWaitNotice } from './ModelWaitNotice';

vi.mock('../../i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }));

it('offers more time only for a slow, extendable wait', () => {
  for (const stage of ['waiting', 'slow', 'extended'] as const) {
    const html = renderToStaticMarkup(
      <ModelWaitNotice
        wait={{ stage, waitId: 'w', canExtend: stage !== 'extended' }}
        onExtend={async () => true}
      />
    );
    expect(html.includes('<button')).toBe(stage === 'slow');
    expect(html).toContain('role="status"');
  }
  const html = renderToStaticMarkup(
    <ModelWaitNotice
      wait={{ stage: 'slow', waitId: 'w', canExtend: false }}
      onExtend={async () => false}
    />
  );
  expect(html).not.toContain('<button');
});
