import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SettingsCard, SettingsListItem } from './SettingsCard';

describe('shared settings surfaces', () => {
  it.each([SettingsCard, SettingsListItem])(
    'keeps content on a solid untextured surface',
    (Card) => {
      const html = renderToStaticMarkup(<Card>Readable content</Card>);
      expect(html).toContain('bg-white');
      expect(html).toContain('dark:bg-zinc-');
      expect(html).not.toContain('radial-gradient');
      expect(html).not.toContain('bg-transparent');
      expect(html).toContain('Readable content');
    }
  );
});
