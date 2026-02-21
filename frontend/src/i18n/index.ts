import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import { en } from './messages/en';
import { zhCN } from './messages/zh-CN';

export type Locale = 'en' | 'zh-CN';

export const STORAGE_KEY = 'suzent.locale';

const SUPPORTED_LOCALES: readonly Locale[] = ['en', 'zh-CN'] as const;

type MessageValue = string | { [k: string]: MessageValue };
type Messages = Record<Locale, MessageValue>;

const messages: Messages = {
  en,
  'zh-CN': zhCN,
};

function isLocale(v: unknown): v is Locale {
  return typeof v === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(v);
}

function normalizeLocale(input: string | null | undefined): Locale {
  const v = (input ?? '').trim();
  if (!v) return 'en';
  if (isLocale(v)) return v;

  const lower = v.toLowerCase();

  if (lower === 'zh' || lower.startsWith('zh-')) return 'zh-CN';
  if (lower === 'en' || lower.startsWith('en-')) return 'en';

  return 'en';
}

function getNavigatorLocale(): Locale {
  const langs = typeof navigator !== 'undefined' ? navigator.languages : undefined;
  if (langs && langs.length > 0) return normalizeLocale(langs[0]);
  const lang = typeof navigator !== 'undefined' ? navigator.language : undefined;
  return normalizeLocale(lang);
}

export function getStoredLocale(): Locale | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (!v) return null;
    return normalizeLocale(v);
  } catch {
    return null;
  }
}

export function setStoredLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    return;
  }
}

export function getInitialLocale(): Locale {
  const stored = getStoredLocale();
  if (stored) return stored;
  return getNavigatorLocale();
}

function getByKey(table: MessageValue, key: string): string | undefined {
  const parts = key.split('.').filter(Boolean);
  let cur: MessageValue = table;

  for (const part of parts) {
    if (typeof cur !== 'object' || cur == null) return undefined;
    const next = (cur as any)[part] as MessageValue | undefined;
    if (next === undefined) return undefined;
    cur = next;
  }

  return typeof cur === 'string' ? cur : undefined;
}

function interpolate(template: string, params?: Record<string, unknown>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k: string) => {
    if (!(k in params)) return `{${k}}`;
    const v = params[k];
    return v == null ? '' : String(v);
  });
}

export function tForLocale(
  locale: Locale,
  key: string,
  params?: Record<string, unknown>,
): string {
  const primary = getByKey(messages[locale], key);
  if (primary != null) return interpolate(primary, params);

  const fallback = getByKey(messages.en, key);
  if (fallback != null) return interpolate(fallback, params);

  return key;
}

type I18nContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider(props: { children: React.ReactNode }): React.ReactElement {
  const [locale, setLocaleState] = useState<Locale>(() => getInitialLocale());

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    setStoredLocale(next);
  }, []);

  const t = useCallback((key: string, params?: Record<string, unknown>) => {
    return tForLocale(locale, key, params);
  }, [locale]);

  const value = useMemo<I18nContextValue>(() => ({
    locale,
    setLocale,
    t,
  }), [locale, setLocale, t]);

  return React.createElement(I18nContext.Provider, { value }, props.children);
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
