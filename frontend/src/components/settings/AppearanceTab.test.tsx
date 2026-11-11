import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nProvider, setStoredLocale } from '../../i18n';
import { ThemeProvider } from '../../hooks/useTheme';
import {
  DEFAULT_APPEARANCE_PREFERENCES,
  writeAppearancePreferences,
} from '../../lib/appearancePreferences';
import { AppearanceTab } from './AppearanceTab';

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
  };
}

function renderAppearance(locale: 'en' | 'zh-CN'): string {
  setStoredLocale(locale);
  return renderToStaticMarkup(
    <I18nProvider>
      <ThemeProvider>
        <AppearanceTab />
      </ThemeProvider>
    </I18nProvider>
  );
}

describe('AppearanceTab', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage());
    writeAppearancePreferences(DEFAULT_APPEARANCE_PREFERENCES);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders all 5 typography, width, and motion rows with default Chinese labels', () => {
    const html = renderAppearance('zh-CN');

    expect(html).toContain('界面字体');
    expect(html).toContain('系统默认');
    expect(html).toContain('回复字体');
    expect(html).toContain('与界面一致');
    expect(html).toContain('对话记录文字大小');
    expect(html).toContain('对话记录宽度');
    expect(html).toContain('动效');
    expect(html).toContain('跟随系统');
  });

  it('renders all 5 typography, width, and motion rows with English labels', () => {
    const html = renderAppearance('en');

    expect(html).toContain('Interface font');
    expect(html).toContain('System default');
    expect(html).toContain('Reply font');
    expect(html).toContain('Same as interface');
    expect(html).toContain('Chat history text size');
    expect(html).toContain('Medium');
    expect(html).toContain('Chat history width');
    expect(html).toContain('Motion');
    expect(html).toContain('Follow system');
  });

  it('shows custom local font combined with fallback preset when configured', () => {
    writeAppearancePreferences({
      ...DEFAULT_APPEARANCE_PREFERENCES,
      uiFont: 'sans',
      customUiFontFamily: 'HarmonyOS Sans SC',
      replyFont: 'serif',
      chatFontSize: 'large',
      chatWidth: 'narrow',
      motion: 'reduced',
    });

    const html = renderAppearance('zh-CN');

    expect(html).toContain('HarmonyOS Sans SC · 无衬线');
    expect(html).toContain('衬线');
    expect(html).toContain('大');
    expect(html).toContain('窄');
    expect(html).toContain('减弱');
  });
});
