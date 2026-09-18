import {
  createContext,
  useContext,
  useEffect,
  useState,
  createElement,
  type ReactNode,
} from 'react';

export type Theme = 'light' | 'dark';
/**
 * What the user asked for, as opposed to what is on screen.
 *
 * `system` is the difference between the two: it follows the OS and keeps
 * following it, so a machine that turns dark in the evening takes Suzent with
 * it. The stored value used to be a `Theme`, and still reads as one.
 */
export type ThemeMode = Theme | 'system';
export type Scheme = 'warm' | 'cold' | 'green';

/** Accent colors shown on interactive elements, headers, buttons */
export const SCHEME_COLORS: Record<Scheme, { light: string; dark: string }> = {
  warm: { light: '#FFE666', dark: '#FF6600' },
  cold: { light: '#7DD3FC', dark: '#38BDF8' },
  green: { light: '#86EFAC', dark: '#4ADE80' },
};

/** Dark-mode surface colors used in card previews (mirrors CSS overrides below) */
export const SCHEME_SURFACES: Record<Scheme, { bg1: string; bg2: string; bg3: string }> = {
  warm: { bg1: '#18181b', bg2: '#27272a', bg3: '#3f3f46' },
  cold: { bg1: '#14161e', bg2: '#1e222e', bg3: '#2b3040' },
  green: { bg1: '#131816', bg2: '#202622', bg3: '#2d352e' },
};

const SYSTEM_DARK = '(prefers-color-scheme: dark)';

function prefersDark(): boolean {
  try {
    return window.matchMedia(SYSTEM_DARK).matches;
  } catch {
    return false;
  }
}

function getInitialMode(): ThemeMode {
  try {
    const stored = localStorage.getItem('suzent-theme') as ThemeMode | null;
    if (stored === 'dark' || stored === 'light' || stored === 'system') return stored;
  } catch {
    /* storage blocked */
  }
  // Nothing stored is not the same as no preference: before there was a mode to
  // store, first run read the OS once and then froze. Following it is what that
  // was reaching for.
  return 'system';
}

function getInitialScheme(): Scheme {
  try {
    const stored = localStorage.getItem('suzent-scheme') as Scheme | null;
    if (stored === 'warm' || stored === 'cold' || stored === 'green') return stored;
    // Migrate from previous per-color localStorage keys
    const oldDark = localStorage.getItem('suzent-color-dark');
    if (oldDark?.toLowerCase() === '#38bdf8') return 'cold';
    if (oldDark?.toLowerCase() === '#4ade80') return 'green';
  } catch {
    /* storage blocked */
  }
  return 'warm';
}

interface ThemeContextValue {
  /** What is on screen: `mode` with `system` already resolved. */
  theme: Theme;
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  toggleTheme: () => void;
  scheme: Scheme;
  setScheme: (s: Scheme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(getInitialMode);
  const [systemDark, setSystemDark] = useState<boolean>(prefersDark);
  const [scheme, setSchemeState] = useState<Scheme>(getInitialScheme);

  const theme: Theme = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;

  // Subscribed whatever the mode, so switching to `system` shows the OS
  // preference as it is now rather than as it was when the app started.
  useEffect(() => {
    let query: MediaQueryList;
    try {
      query = window.matchMedia(SYSTEM_DARK);
    } catch {
      return;
    }
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    setSystemDark(query.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem('suzent-theme', mode);
    } catch {
      /* storage blocked */
    }
  }, [mode]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.scheme = scheme;
    const color = theme === 'dark' ? SCHEME_COLORS[scheme].dark : SCHEME_COLORS[scheme].light;
    root.style.setProperty('--brutal-yellow', color);
    try {
      localStorage.setItem('suzent-scheme', scheme);
    } catch {
      /* storage blocked */
    }
  }, [theme, scheme]);

  function setScheme(s: Scheme) {
    setSchemeState(s);
  }
  function setMode(m: ThemeMode) {
    setModeState(m);
  }
  /** Flips what is on screen, which means leaving `system` behind. */
  function toggleTheme() {
    setModeState(theme === 'dark' ? 'light' : 'dark');
  }

  return createElement(
    ThemeContext.Provider,
    { value: { theme, mode, setMode, toggleTheme, scheme, setScheme } },
    children
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
