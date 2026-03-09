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
  cold:  { bg1: '#0c1829', bg2: '#122035', bg3: '#1a2e47' },
  green: { bg1: '#0a1a0f', bg2: '#101f16', bg3: '#172b1e' },
};

function getInitialTheme(): Theme {
  const stored = localStorage.getItem('suzent-theme') as Theme | null;
  if (stored === 'dark' || stored === 'light') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getInitialScheme(): Scheme {
  const stored = localStorage.getItem('suzent-scheme') as Scheme | null;
  if (stored === 'warm' || stored === 'cold' || stored === 'green') return stored;
  // Migrate from previous per-color localStorage keys
  const oldDark = localStorage.getItem('suzent-color-dark');
  if (oldDark?.toLowerCase() === '#38bdf8') return 'cold';
  if (oldDark?.toLowerCase() === '#4ade80') return 'green';
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
    localStorage.setItem('suzent-theme', theme);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.scheme = scheme;
    const color = theme === 'dark' ? SCHEME_COLORS[scheme].dark : SCHEME_COLORS[scheme].light;
    root.style.setProperty('--brutal-yellow', color);
    localStorage.setItem('suzent-scheme', scheme);
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
