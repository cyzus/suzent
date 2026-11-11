import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  APPEARANCE_STORAGE_KEY,
  CHAT_FONT_METRICS,
  CHAT_WIDTH_VALUES,
  DEFAULT_APPEARANCE_PREFERENCES,
  REPLY_SERIF_FONT_STACK,
  UI_FONT_STACKS,
  applyAppearancePreferencesToDocument,
  isLocalFontPickerSupported,
  isReducedMotionActive,
  normalizeLocalFontFamilies,
  queryAvailableLocalFonts,
  readAppearancePreferences,
  resolveReplyFontStack,
  resolveUiFontStack,
  updateAppearancePreferences,
  writeAppearancePreferences,
} from './appearancePreferences';

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

describe('appearancePreferences', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createMemoryStorage());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns default preferences when storage is empty or malformed', () => {
    expect(readAppearancePreferences()).toEqual(DEFAULT_APPEARANCE_PREFERENCES);

    localStorage.setItem(APPEARANCE_STORAGE_KEY, '{not-json');
    expect(readAppearancePreferences()).toEqual(DEFAULT_APPEARANCE_PREFERENCES);

    localStorage.setItem(
      APPEARANCE_STORAGE_KEY,
      JSON.stringify({
        uiFont: 'invalid',
        customUiFontFamily: '@SimSun',
        replyFont: 'unknown',
        chatFontSize: 'huge',
        chatWidth: 'ultra',
        motion: 'off',
      })
    );
    expect(readAppearancePreferences()).toEqual(DEFAULT_APPEARANCE_PREFERENCES);
  });

  it('resolves interface font stacks and appends the preset stack after a local font', () => {
    expect(resolveUiFontStack('system')).toBe(UI_FONT_STACKS.system);
    expect(resolveUiFontStack('sans')).toBe(UI_FONT_STACKS.sans);
    expect(resolveUiFontStack('mono')).toBe(UI_FONT_STACKS.mono);

    const custom = resolveUiFontStack('sans', 'LXGW WenKai');
    expect(custom).toBe(`"LXGW WenKai", ${UI_FONT_STACKS.sans}`);

    // Vertical `@`-prefixed CJK fonts and unsafe characters are stripped/ignored
    expect(resolveUiFontStack('system', '@Microsoft YaHei')).toBe(UI_FONT_STACKS.system);
  });

  it('resolves reply font stacks inheriting UI font by default', () => {
    const uiStack = resolveUiFontStack('sans', 'HarmonyOS Sans SC');
    expect(resolveReplyFontStack('match-ui', uiStack)).toBe(uiStack);
    expect(resolveReplyFontStack('serif', uiStack)).toBe(REPLY_SERIF_FONT_STACK);
    expect(resolveReplyFontStack('mono', uiStack)).toBe(UI_FONT_STACKS.mono);
  });

  it('normalizes local fonts by filtering @-prefixed names, deduplicating, and sorting', () => {
    const raw = [
      { family: 'Segoe UI' },
      { family: '@Microsoft YaHei' },
      { family: 'Microsoft YaHei' },
      { family: 'Consolas' },
      { family: 'microsoft yahei' },
      { family: '@SimSun' },
      { family: 'PingFang SC' },
      { family: '   ' },
    ];
    const normalized = normalizeLocalFontFamilies(raw);
    expect(normalized).toEqual([
      'Consolas',
      'Microsoft YaHei',
      'microsoft yahei',
      'PingFang SC',
      'Segoe UI',
    ]);
    expect(normalized.some((f) => f.startsWith('@'))).toBe(false);
  });

  it('detects queryLocalFonts support and hides on macOS WKWebView or missing API', async () => {
    expect(isLocalFontPickerSupported(undefined)).toBe(false);
    expect(isLocalFontPickerSupported({} as Window)).toBe(false);

    const macWkWebView = {
      queryLocalFonts: async () => [{ family: 'SF Pro' }],
      navigator: {
        userAgent:
          'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)',
      },
    } as unknown as Window;
    expect(isLocalFontPickerSupported(macWkWebView)).toBe(false);

    const chromiumWin = {
      queryLocalFonts: async () => [
        { family: 'JetBrains Mono' },
        { family: '@SimHei' },
        { family: 'Inter' },
      ],
      navigator: {
        userAgent:
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
      },
    } as unknown as Window;
    expect(isLocalFontPickerSupported(chromiumWin)).toBe(true);
    await expect(queryAvailableLocalFonts(chromiumWin)).resolves.toEqual([
      'Inter',
      'JetBrains Mono',
    ]);
  });

  it('applies dataset attributes and CSS custom properties to the root element', () => {
    const styleMap = new Map<string, string>();
    const fakeRoot = {
      dataset: {} as DOMStringMap,
      style: {
        setProperty: (key: string, val: string) => {
          styleMap.set(key, val);
        },
      },
    } as unknown as HTMLElement;

    const prefs = {
      uiFont: 'sans' as const,
      customUiFontFamily: 'MiSans',
      replyFont: 'serif' as const,
      chatFontSize: 'large' as const,
      chatWidth: 'narrow' as const,
      motion: 'reduced' as const,
    };

    applyAppearancePreferencesToDocument(prefs, fakeRoot);

    expect(fakeRoot.dataset.uiFont).toBe('sans');
    expect(fakeRoot.dataset.customUiFont).toBe('MiSans');
    expect(fakeRoot.dataset.replyFont).toBe('serif');
    expect(fakeRoot.dataset.chatFontSize).toBe('large');
    expect(fakeRoot.dataset.chatWidth).toBe('narrow');
    expect(fakeRoot.dataset.motion).toBe('reduced');

    expect(styleMap.get('--suzent-font-ui')).toBe(`"MiSans", ${UI_FONT_STACKS.sans}`);
    expect(styleMap.get('--suzent-font-reply')).toBe(REPLY_SERIF_FONT_STACK);
    expect(styleMap.get('--suzent-chat-font-size')).toBe(CHAT_FONT_METRICS.large.fontSize);
    expect(styleMap.get('--suzent-chat-line-height')).toBe(CHAT_FONT_METRICS.large.lineHeight);
    expect(styleMap.get('--suzent-chat-max-width')).toBe(CHAT_WIDTH_VALUES.narrow.assistant);
    expect(styleMap.get('--suzent-chat-user-max-width')).toBe(CHAT_WIDTH_VALUES.narrow.user);
  });

  it('persists updates and resolves reduced motion from either explicit setting or system media query', () => {
    writeAppearancePreferences(DEFAULT_APPEARANCE_PREFERENCES);
    const updated = updateAppearancePreferences({
      chatFontSize: 'small',
      chatWidth: 'wide',
      motion: 'reduced',
    });

    expect(updated.chatFontSize).toBe('small');
    expect(updated.chatWidth).toBe('wide');
    expect(updated.motion).toBe('reduced');
    expect(readAppearancePreferences()).toEqual(updated);
    expect(isReducedMotionActive(updated)).toBe(true);
    expect(isReducedMotionActive({ motion: 'system' })).toBe(false);
  });
});
