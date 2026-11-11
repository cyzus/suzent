/**
 * Device-local typography, layout, and motion preferences for the Appearance tab.
 *
 * Like theme and notification preferences, these govern how this machine
 * renders the interface and conversation transcript, so they live in
 * localStorage and are applied directly to `document.documentElement`.
 */
import { useEffect, useState } from 'react';

export type UiFontPreset = 'system' | 'sans' | 'mono';
export type ReplyFontPreset = 'match-ui' | 'serif' | 'mono';
export type ChatFontSize = 'small' | 'medium' | 'large';
export type ChatWidth = 'narrow' | 'medium' | 'wide';
export type MotionMode = 'system' | 'reduced';

export interface AppearancePreferences {
  uiFont: UiFontPreset;
  /** Optional local font family chosen via `window.queryLocalFonts()`. */
  customUiFontFamily: string | null;
  replyFont: ReplyFontPreset;
  chatFontSize: ChatFontSize;
  chatWidth: ChatWidth;
  motion: MotionMode;
}

export const UI_FONT_OPTIONS: readonly UiFontPreset[] = ['system', 'sans', 'mono'];
export const REPLY_FONT_OPTIONS: readonly ReplyFontPreset[] = ['match-ui', 'serif', 'mono'];
export const CHAT_FONT_SIZE_OPTIONS: readonly ChatFontSize[] = ['small', 'medium', 'large'];
export const CHAT_WIDTH_OPTIONS: readonly ChatWidth[] = ['narrow', 'medium', 'wide'];
export const MOTION_OPTIONS: readonly MotionMode[] = ['system', 'reduced'];

export const DEFAULT_APPEARANCE_PREFERENCES: AppearancePreferences = {
  uiFont: 'system',
  customUiFontFamily: null,
  replyFont: 'match-ui',
  chatFontSize: 'medium',
  chatWidth: 'medium',
  motion: 'system',
};

export const APPEARANCE_STORAGE_KEY = 'suzent-appearance-preferences';

/**
 * Cross-platform fallback font stacks (no bundled CJK font binaries).
 */
export const UI_FONT_STACKS: Record<UiFontPreset, string> = {
  system:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif',
  sans: 'Inter, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", sans-serif',
  mono: 'Consolas, "JetBrains Mono", "Fira Code", "SFMono-Regular", Menlo, Monaco, "Liberation Mono", "Ubuntu Mono", "DejaVu Sans Mono", "PingFang SC", "Microsoft YaHei", monospace',
};

export const REPLY_SERIF_FONT_STACK =
  'Georgia, "Songti SC", "SimSun", "Source Han Serif SC", "Noto Serif CJK SC", "Times New Roman", serif';

export const CHAT_FONT_METRICS: Record<
  ChatFontSize,
  { fontSize: string; lineHeight: string; codeFontSize: string; codeLineHeight: string }
> = {
  small: {
    fontSize: '0.8125rem',
    lineHeight: '1.65',
    codeFontSize: '0.75rem',
    codeLineHeight: '1.5',
  },
  medium: {
    fontSize: '0.875rem',
    lineHeight: '1.75',
    codeFontSize: '0.75rem',
    codeLineHeight: '1.55',
  },
  large: {
    fontSize: '1rem',
    lineHeight: '1.85',
    codeFontSize: '0.84375rem',
    codeLineHeight: '1.6',
  },
};

export const CHAT_WIDTH_VALUES: Record<ChatWidth, { assistant: string; user: string }> = {
  narrow: {
    assistant: 'min(100%, 42rem)',
    user: 'min(100%, 38rem)',
  },
  medium: {
    assistant: 'min(100%, 56rem)',
    user: 'min(100%, 48rem)',
  },
  wide: {
    assistant: 'min(100%, 72rem)',
    user: 'min(100%, 64rem)',
  },
};

const SYSTEM_REDUCED_MOTION = '(prefers-reduced-motion: reduce)';

function isUiFont(value: unknown): value is UiFontPreset {
  return typeof value === 'string' && (UI_FONT_OPTIONS as readonly string[]).includes(value);
}

function isReplyFont(value: unknown): value is ReplyFontPreset {
  return typeof value === 'string' && (REPLY_FONT_OPTIONS as readonly string[]).includes(value);
}

function isChatFontSize(value: unknown): value is ChatFontSize {
  return typeof value === 'string' && (CHAT_FONT_SIZE_OPTIONS as readonly string[]).includes(value);
}

function isChatWidth(value: unknown): value is ChatWidth {
  return typeof value === 'string' && (CHAT_WIDTH_OPTIONS as readonly string[]).includes(value);
}

function isMotionMode(value: unknown): value is MotionMode {
  return typeof value === 'string' && (MOTION_OPTIONS as readonly string[]).includes(value);
}

export function sanitizeFontFamilyName(name: string | null | undefined): string | null {
  if (typeof name !== 'string') return null;
  const cleaned = name.replace(/["'\\;\n\r]/g, '').trim();
  if (!cleaned || cleaned.startsWith('@')) return null;
  return cleaned;
}

export function resolveUiFontStack(preset: UiFontPreset, customFamily?: string | null): string {
  const baseStack = UI_FONT_STACKS[preset] ?? UI_FONT_STACKS.system;
  const safeCustom = sanitizeFontFamilyName(customFamily);
  if (!safeCustom) return baseStack;
  return `"${safeCustom}", ${baseStack}`;
}

export function resolveReplyFontStack(replyPreset: ReplyFontPreset, uiFontStack: string): string {
  if (replyPreset === 'serif') return REPLY_SERIF_FONT_STACK;
  if (replyPreset === 'mono') return UI_FONT_STACKS.mono;
  return uiFontStack;
}

export function readAppearancePreferences(): AppearancePreferences {
  try {
    const raw = localStorage.getItem(APPEARANCE_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<AppearancePreferences>;
      return {
        uiFont: isUiFont(parsed.uiFont) ? parsed.uiFont : DEFAULT_APPEARANCE_PREFERENCES.uiFont,
        customUiFontFamily: sanitizeFontFamilyName(parsed.customUiFontFamily),
        replyFont: isReplyFont(parsed.replyFont)
          ? parsed.replyFont
          : DEFAULT_APPEARANCE_PREFERENCES.replyFont,
        chatFontSize: isChatFontSize(parsed.chatFontSize)
          ? parsed.chatFontSize
          : DEFAULT_APPEARANCE_PREFERENCES.chatFontSize,
        chatWidth: isChatWidth(parsed.chatWidth)
          ? parsed.chatWidth
          : DEFAULT_APPEARANCE_PREFERENCES.chatWidth,
        motion: isMotionMode(parsed.motion) ? parsed.motion : DEFAULT_APPEARANCE_PREFERENCES.motion,
      };
    }
  } catch {
    /* storage blocked or malformed */
  }
  return { ...DEFAULT_APPEARANCE_PREFERENCES };
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emitChange(): void {
  for (const listener of listeners) listener();
}

export function systemPrefersReducedMotion(): boolean {
  try {
    return (
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia(SYSTEM_REDUCED_MOTION).matches
    );
  } catch {
    return false;
  }
}

export function isReducedMotionActive(
  preferences: Pick<AppearancePreferences, 'motion'> = readAppearancePreferences()
): boolean {
  if (preferences.motion === 'reduced') return true;
  return systemPrefersReducedMotion();
}

export function applyAppearancePreferencesToDocument(
  preferences: AppearancePreferences,
  root: HTMLElement | null = typeof document !== 'undefined' ? document.documentElement : null
): void {
  if (!root) return;

  const uiStack = resolveUiFontStack(preferences.uiFont, preferences.customUiFontFamily);
  const replyStack = resolveReplyFontStack(preferences.replyFont, uiStack);
  const fontMetrics = CHAT_FONT_METRICS[preferences.chatFontSize] ?? CHAT_FONT_METRICS.medium;
  const widthMetrics = CHAT_WIDTH_VALUES[preferences.chatWidth] ?? CHAT_WIDTH_VALUES.medium;

  root.dataset.uiFont = preferences.uiFont;
  if (preferences.customUiFontFamily) {
    root.dataset.customUiFont = preferences.customUiFontFamily;
  } else {
    delete root.dataset.customUiFont;
  }
  root.dataset.replyFont = preferences.replyFont;
  root.dataset.chatFontSize = preferences.chatFontSize;
  root.dataset.chatWidth = preferences.chatWidth;
  root.dataset.motion = preferences.motion;

  root.style.setProperty('--suzent-font-ui', uiStack);
  root.style.setProperty('--suzent-font-reply', replyStack);
  root.style.setProperty('--suzent-chat-font-size', fontMetrics.fontSize);
  root.style.setProperty('--suzent-chat-line-height', fontMetrics.lineHeight);
  root.style.setProperty('--suzent-chat-code-font-size', fontMetrics.codeFontSize);
  root.style.setProperty('--suzent-chat-code-line-height', fontMetrics.codeLineHeight);
  root.style.setProperty('--suzent-chat-max-width', widthMetrics.assistant);
  root.style.setProperty('--suzent-chat-user-max-width', widthMetrics.user);
}

export function writeAppearancePreferences(preferences: AppearancePreferences): void {
  try {
    localStorage.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    /* storage blocked */
  }
  applyAppearancePreferencesToDocument(preferences);
  emitChange();
}

export function updateAppearancePreferences(
  patch: Partial<AppearancePreferences>
): AppearancePreferences {
  const next: AppearancePreferences = {
    ...readAppearancePreferences(),
    ...patch,
  };
  writeAppearancePreferences(next);
  return next;
}

interface LocalFontData {
  family?: string;
}

type QueryLocalFontsWindow = Window & {
  queryLocalFonts?: () => Promise<LocalFontData[]>;
};

const MACOS_WEBKIT_UA_RE = /Macintosh.*AppleWebKit/i;
const CHROMIUM_UA_RE = /Chrome|Chromium|Edg\//i;

/**
 * Whether the current browser/WebView supports enumerating local fonts via
 * `window.queryLocalFonts()`. Automatically hidden on environments without the
 * API (such as macOS WKWebView, Firefox, or mobile WebViews).
 */
export function isLocalFontPickerSupported(
  win: QueryLocalFontsWindow | undefined = typeof window !== 'undefined'
    ? (window as QueryLocalFontsWindow)
    : undefined
): boolean {
  if (!win || typeof win.queryLocalFonts !== 'function') return false;
  try {
    const ua = win.navigator?.userAgent ?? '';
    if (MACOS_WEBKIT_UA_RE.test(ua) && !CHROMIUM_UA_RE.test(ua)) {
      return false;
    }
  } catch {
    /* ignore navigator access errors */
  }
  return true;
}

/**
 * Filter `@`-prefixed vertical CJK font variants, deduplicate, and sort local
 * font families alphabetically.
 */
export function normalizeLocalFontFamilies(fonts: Iterable<LocalFontData | string>): string[] {
  const unique = new Set<string>();
  for (const item of fonts) {
    const raw = typeof item === 'string' ? item : item?.family;
    const sanitized = sanitizeFontFamilyName(raw);
    if (sanitized) {
      unique.add(sanitized);
    }
  }
  return Array.from(unique).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

export async function queryAvailableLocalFonts(
  win: QueryLocalFontsWindow | undefined = typeof window !== 'undefined'
    ? (window as QueryLocalFontsWindow)
    : undefined
): Promise<string[]> {
  if (!isLocalFontPickerSupported(win) || !win?.queryLocalFonts) return [];
  const fonts = await win.queryLocalFonts();
  return normalizeLocalFontFamilies(fonts);
}

export interface AppearancePreferencesApi {
  preferences: AppearancePreferences;
  reducedMotion: boolean;
  setUiFont: (uiFont: UiFontPreset, customUiFontFamily?: string | null) => void;
  setReplyFont: (replyFont: ReplyFontPreset) => void;
  setChatFontSize: (chatFontSize: ChatFontSize) => void;
  setChatWidth: (chatWidth: ChatWidth) => void;
  setMotion: (motion: MotionMode) => void;
}

export function useAppearancePreferences(): AppearancePreferencesApi {
  const [preferences, setPreferences] = useState<AppearancePreferences>(readAppearancePreferences);
  const [systemReduced, setSystemReduced] = useState<boolean>(systemPrefersReducedMotion);

  useEffect(() => {
    applyAppearancePreferencesToDocument(readAppearancePreferences());
    return subscribe(() => setPreferences(readAppearancePreferences()));
  }, []);

  useEffect(() => {
    let query: MediaQueryList;
    try {
      query = window.matchMedia(SYSTEM_REDUCED_MOTION);
    } catch {
      return;
    }
    const onChange = (event: MediaQueryListEvent) => setSystemReduced(event.matches);
    setSystemReduced(query.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  const reducedMotion = preferences.motion === 'reduced' || systemReduced;

  return {
    preferences,
    reducedMotion,
    setUiFont: (uiFont, customUiFontFamily = null) =>
      updateAppearancePreferences({
        uiFont,
        customUiFontFamily: sanitizeFontFamilyName(customUiFontFamily),
      }),
    setReplyFont: (replyFont) => updateAppearancePreferences({ replyFont }),
    setChatFontSize: (chatFontSize) => updateAppearancePreferences({ chatFontSize }),
    setChatWidth: (chatWidth) => updateAppearancePreferences({ chatWidth }),
    setMotion: (motion) => updateAppearancePreferences({ motion }),
  };
}
