import { createContext, useContext, useEffect, useState, createElement, type ReactNode } from 'react';

export type Theme = 'light' | 'dark';
export type Scheme = 'warm' | 'cold' | 'green';

/** Accent colors shown on interactive elements, headers, buttons */
export const SCHEME_COLORS: Record<Scheme, { light: string; dark: string }> = {
  warm:  { light: '#FFE666', dark: '#FF6600' },
  cold:  { light: '#7DD3FC', dark: '#38BDF8' },
  green: { light: '#86EFAC', dark: '#4ADE80' },
};

/** Dark-mode surface colors used in card previews (mirrors CSS overrides below) */
export const SCHEME_SURFACES: Record<Scheme, { bg1: string; bg2: string; bg3: string }> = {
  warm:  { bg1: '#18181b', bg2: '#27272a', bg3: '#3f3f46' },
  cold:  { bg1: '#14161e', bg2: '#1e222e', bg3: '#2b3040' },
  green: { bg1: '#131816', bg2: '#202622', bg3: '#2d352e' },
};

function getInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem('suzent-theme') as Theme | null;
    if (stored === 'dark' || stored === 'light') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function getInitialScheme(): Scheme {
  try {
    const stored = localStorage.getItem('suzent-scheme') as Scheme | null;
    if (stored === 'warm' || stored === 'cold' || stored === 'green') return stored;
    // Migrate from previous per-color localStorage keys
    const oldDark = localStorage.getItem('suzent-color-dark');
    if (oldDark?.toLowerCase() === '#38bdf8') return 'cold';
    if (oldDark?.toLowerCase() === '#4ade80') return 'green';
  } catch { /* storage blocked */ }
  return 'warm';
}

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  scheme: Scheme;
  setScheme: (s: Scheme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [scheme, setSchemeState] = useState<Scheme>(getInitialScheme);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    try { localStorage.setItem('suzent-theme', theme); } catch { /* storage blocked */ }
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.scheme = scheme;
    const color = theme === 'dark' ? SCHEME_COLORS[scheme].dark : SCHEME_COLORS[scheme].light;
    root.style.setProperty('--brutal-yellow', color);
    try { localStorage.setItem('suzent-scheme', scheme); } catch { /* storage blocked */ }
  }, [theme, scheme]);

  function setScheme(s: Scheme) { setSchemeState(s); }
  function toggleTheme() { setTheme(t => (t === 'dark' ? 'light' : 'dark')); }

  return createElement(
    ThemeContext.Provider,
    { value: { theme, toggleTheme, scheme, setScheme } },
    children,
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
