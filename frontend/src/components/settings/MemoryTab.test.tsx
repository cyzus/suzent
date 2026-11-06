import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { I18nProvider } from '../../i18n';
import { MemoryTab } from './MemoryTab';

describe('memory settings', () => {
  it('keeps the memory controls and models without exposing host mounts', () => {
    const html = renderToStaticMarkup(
      <I18nProvider>
        <MemoryTab
          memoryEnabled
          onMemoryEnabledChange={() => {}}
          embeddingModel="provider/embedding"
          extractionModel="provider/extraction"
          onOpenModelRoles={() => {}}
        />
      </I18nProvider>
    );
    expect(html).toContain('provider/embedding');
    expect(html).toContain('provider/extraction');
    expect(html).toContain('Model Roles');
    expect(html).not.toContain('/mnt/');
    expect(html).not.toContain('Host folder');
    expect(html).not.toContain('Choose folder');
  });
});
