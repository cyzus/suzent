import { createContext, useContext, useEffect, useState, createElement, type ReactNode } from 'react';

export type Theme = 'light' | 'dark';

const DEFAULT_LIGHT_COLOR = '#FFE666';
const DEFAULT_DARK_COLOR = '#FF6600';

function getInitialTheme(): Theme {
  const stored = localStorage.getItem('suzent-theme') as Theme | null;
  if (stored === 'dark' || stored === 'light') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getInitialLightColor(): string {
  return localStorage.getItem('suzent-color-light') || DEFAULT_LIGHT_COLOR;
}

function getInitialDarkColor(): string {
  return localStorage.getItem('suzent-color-dark') || DEFAULT_DARK_COLOR;
}

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
  lightColor: string;
  darkColor: string;
  setLightColor: (color: string) => void;
  setDarkColor: (color: string) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [lightColor, setLightColorState] = useState<string>(getInitialLightColor);
  const [darkColor, setDarkColorState] = useState<string>(getInitialDarkColor);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    localStorage.setItem('suzent-theme', theme);
  }, [theme]);

  useEffect(() => {
    const color = theme === 'dark' ? darkColor : lightColor;
    document.documentElement.style.setProperty('--brutal-yellow', color);
  }, [theme, lightColor, darkColor]);

  function setLightColor(color: string) {
    setLightColorState(color);
    localStorage.setItem('suzent-color-light', color);
  }

  function setDarkColor(color: string) {
    setDarkColorState(color);
    localStorage.setItem('suzent-color-dark', color);
  }

  function toggleTheme() {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'));
  }

  return createElement(
    ThemeContext.Provider,
    { value: { theme, toggleTheme, lightColor, darkColor, setLightColor, setDarkColor } },
    children,
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
